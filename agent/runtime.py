"""Instances: a definition made runnable, with its own root, log, limits and lifecycle."""
import asyncio
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from opentelemetry import trace

from agent.config import AgentConfig, build_options, digest, preflight
from agent.events import EventLog
from agent.evidence import TRAIL, Evidence
from agent.policy import Decision, Gate, args_digest, make_hooks

ROOT = Path(__file__).resolve().parent.parent
INSTANCES = ROOT / "instances"


class Status(str, Enum):
    created = "created"
    running = "running"
    finished = "finished"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class Instance:
    id: str
    cfg: AgentConfig
    principal: str
    root: Path
    log: EventLog
    evidence: Evidence
    status: Status = Status.created
    created_at: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    result: str | None = None
    error: str | None = None
    turns: int = 0
    cost_usd: float | None = None
    incidents: int = 0

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.cfg.name, "principal": self.principal,
            "status": self.status.value, "created_at": self.created_at,
            "turns": self.turns, "cost_usd": self.cost_usd, "incidents": self.incidents,
            "result": self.result, "error": self.error,
        }

    def record_decision(self, tool: str, tool_input: dict, decision: Decision) -> None:
        """Every gate decision is an event and a signed record; every denial is also an incident."""
        evidence = self.evidence.record(self.cfg.name, self.id, self.cfg.policy.version, tool, tool_input, decision)
        self.log.emit("policy.decision", tool=tool, rule=decision.rule, allow=decision.allow,
                      args_digest=args_digest(tool_input), evidence=evidence)
        if evidence is None:
            self.incidents += 1
            self.log.emit("incident", severity="high", rule="evidence:no_receipt", tool=tool,
                          reason="the decision was made and no signed receipt was written for it",
                          args_digest=args_digest(tool_input), policy_version=self.cfg.policy.version)
        if not decision.allow:
            self.incidents += 1
            self.log.emit("incident", severity=decision.severity, rule=decision.rule, tool=tool,
                          reason=decision.reason, args_digest=args_digest(tool_input),
                          policy_version=self.cfg.policy.version)


class Registry:
    """Live table of instances. Everything the panel and the CLI do goes through here."""

    def __init__(self, base: Path = INSTANCES, trail: Path = TRAIL) -> None:
        self.base = base
        self.evidence = Evidence(trail)
        self.instances: dict[str, Instance] = {}

    def create(self, cfg: AgentConfig, principal: str = "local") -> Instance:
        iid = f"{cfg.name}-{uuid.uuid4().hex[:8]}"
        root = self.base / iid
        (root / "work").mkdir(parents=True, exist_ok=True)
        inst = Instance(iid, cfg, principal, root, EventLog(root / "events.jsonl", iid), self.evidence)
        inst.log.emit("instance.created", definition=digest(cfg), principal=principal)
        self.evidence.lifecycle(iid, "instance.create", agent=cfg.name, definition=digest(cfg),
                                policy_version=cfg.policy.version, model=cfg.model, principal=principal)
        self.instances[iid] = inst
        return inst

    def get(self, iid: str) -> Instance:
        return self.instances[iid]

    def list(self) -> list[dict]:
        return [i.summary() for i in self.instances.values()]

    def start(self, iid: str) -> Instance:
        inst = self.get(iid)
        if inst.status is Status.running:
            return inst
        inst.status = Status.running
        self.evidence.lifecycle(iid, "run.start")
        inst.task = asyncio.create_task(self._run(inst))
        return inst

    def stop(self, iid: str) -> Instance:
        inst = self.get(iid)
        if inst.task and not inst.task.done():
            inst.task.cancel()
        return inst

    def delete(self, iid: str) -> None:
        inst = self.get(iid)
        if inst.status is Status.running:
            raise RuntimeError("stop the instance before deleting it")
        # The folder and its event log go; this record in the chain stays.
        self.evidence.lifecycle(iid, "instance.delete", status=inst.status.value)
        shutil.rmtree(inst.root, ignore_errors=True)
        del self.instances[iid]

    async def _run(self, inst: Instance) -> None:
        try:
            await asyncio.wait_for(run_loop(inst), timeout=inst.cfg.timeout_s)
            inst.status = Status.finished
        except asyncio.CancelledError:
            inst.status = Status.cancelled
            inst.log.emit("run.cancelled")
        except asyncio.TimeoutError:
            inst.status = Status.failed
            inst.error = f"timeout after {inst.cfg.timeout_s}s"
            inst.log.emit("run.failed", error=inst.error)
        except (Exception, SystemExit) as exc:
            inst.status = Status.failed
            inst.error = str(exc) or repr(exc)
            inst.log.emit("run.failed", error=inst.error)
        self.evidence.lifecycle(inst.id, "run.end", status=inst.status.value, turns=inst.turns,
                                cost_usd=inst.cost_usd, incidents=inst.incidents, error=inst.error)


async def run_loop(inst: Instance) -> None:
    """One pass of the agent loop for this instance, every step printed, logged and traced."""
    cfg, log = inst.cfg, inst.log
    preflight(cfg)
    tr = trace.get_tracer("mainsheet")
    gate = Gate(cfg.policy)
    options = build_options(cfg, inst.root / "work", hooks=make_hooks(gate, inst.record_decision))
    open_tools: dict[str, trace.Span] = {}
    with tr.start_as_current_span("invoke_agent") as run:
        run.set_attribute("gen_ai.operation.name", "invoke_agent")
        run.set_attribute("gen_ai.agent.name", cfg.name)
        run.set_attribute("gen_ai.request.model", cfg.model)
        run.set_attribute("mainsheet.instance", inst.id)
        run.set_attribute("mainsheet.principal", inst.principal)
        log.emit("run.started", task=cfg.task, model=cfg.model, principal=inst.principal)
        async for message in query(prompt=cfg.task, options=options):
            if isinstance(message, AssistantMessage):
                inst.turns += 1
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        span = tr.start_span(f"execute_tool {block.name}")
                        span.set_attribute("gen_ai.operation.name", "execute_tool")
                        span.set_attribute("gen_ai.tool.name", block.name)
                        span.set_attribute("gen_ai.tool.call.id", block.id)
                        open_tools[block.id] = span
                        print(f"[{inst.id} {inst.turns}] tool {block.name} {block.input}")
                        log.emit("tool.called", name=block.name, input=block.input)
                    elif isinstance(block, TextBlock):
                        print(f"[{inst.id} {inst.turns}] {block.text.strip()}")
                        log.emit("text", text=block.text)
            elif isinstance(message, UserMessage):
                for block in message.content:
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in open_tools:
                        span = open_tools.pop(block.tool_use_id)
                        error = bool(getattr(block, "is_error", False))
                        if error:
                            span.set_status(trace.StatusCode.ERROR)
                        span.end()
                        log.emit("tool.returned", id=block.tool_use_id, error=error)
            elif isinstance(message, ResultMessage):
                inst.cost_usd = getattr(message, "total_cost_usd", None)
                inst.result = message.result
                if inst.cost_usd is not None and inst.cost_usd > cfg.policy.budgets.max_cost_usd:
                    inst.incidents += 1
                    log.emit("incident", severity="medium", rule="budget:cost_usd", tool="",
                             reason=f"run cost {inst.cost_usd:.4f} exceeded {cfg.policy.budgets.max_cost_usd}",
                             policy_version=cfg.policy.version)
                usage = getattr(message, "usage", None) or {}
                run.set_attribute("gen_ai.usage.input_tokens", usage.get("input_tokens", 0))
                run.set_attribute("gen_ai.usage.output_tokens", usage.get("output_tokens", 0))
                run.set_attribute("mainsheet.cost_usd", inst.cost_usd or 0.0)
                run.set_attribute("mainsheet.turns", inst.turns)
                print(f"\n[{inst.id}] result: {message.result}\nturns: {inst.turns}  cost_usd: {inst.cost_usd}")
                log.emit("run.ended", result=message.result, turns=inst.turns, cost_usd=inst.cost_usd, usage=usage)
