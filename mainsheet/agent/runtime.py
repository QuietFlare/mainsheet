"""Instances: a definition made runnable, with its own root, log, limits and lifecycle."""
import asyncio
import contextlib
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)
from opentelemetry import trace

from mainsheet.agent.config import AgentConfig, build_options, credential, digest, preflight
from mainsheet.agent.events import EventLog
from mainsheet.agent.evidence import TRAIL, Evidence
from mainsheet.agent.policy import Decision, Gate, args_digest, make_hooks, short_name
from mainsheet.agent.tools import human
from mainsheet.paths import HOME

INSTANCES = HOME / "instances"

# Where the harness keeps a session's transcript: one folder per working directory, the path
# with every separator turned into a dash, and one <session id>.jsonl inside it.
HARNESS_PROJECTS = Path.home() / ".claude" / "projects"

# What a resumed run is told. The restored conversation already holds the task and everything
# the previous run did; repeating the task would start it over.
RESUME_PROMPT = "Continue the task from where the previous run stopped. Do not repeat work already done. Then stop."


def events_of(root: Path) -> list[dict]:
    """Every event the instance has logged, oldest first. An instance with no log has none."""
    path = root / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def session_of(root: Path, projects: Path = HARNESS_PROJECTS) -> str | None:
    """The harness session id of the instance's last run.

    Taken from the instance's own log when a run recorded it, else from the harness's transcript
    folder for the instance's work directory, so runs older than this feature can still be resumed.
    """
    recorded = [e["session_id"] for e in events_of(root) if e.get("session_id")]
    if recorded:
        return recorded[-1]
    folder = projects / str((root / "work").resolve()).replace("/", "-")
    transcripts = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if folder.exists() else []
    return transcripts[-1].stem if transcripts else None


def session_cost_of(root: Path) -> float:
    """What the harness session had cost by the end of the instance's last run, from its log."""
    for event in reversed(events_of(root)):
        if event.get("kind") == "run.ended":
            total = event.get("session_cost_usd", event.get("cost_usd"))
            return float(total or 0.0)
    return 0.0


def tainted_before(root: Path, policy) -> bool:
    """Whether any earlier run of this instance consumed untrusted output. Taint carries across runs."""
    for event in events_of(root):
        if event.get("kind") != "tool.called":
            continue
        rule = policy.tools.get(short_name(event.get("name", "")))
        if rule and rule.untrusted_output:
            return True
    return False

# The harness ends a run with this result subtype when policy.budgets.max_cost_usd is reached.
# The cap is passed to it in build_options, so the stop happens mid-run, not in a report at the end.
BUDGET_STOP = "error_max_budget_usd"


def stopped_at_cap(result) -> bool:
    """True when a result message or a ResultError says the run ended on the cost cap."""
    return getattr(result, "subtype", None) == BUDGET_STOP


async def messages(prompt: str, options, log: EventLog, stream=query):
    """The harness's messages, one by one. A cost-cap stop ends the stream; any other error result still raises."""
    try:
        async for message in stream(prompt=prompt, options=options):
            yield message
    except ResultError as exc:
        if not stopped_at_cap(exc):
            raise
        log.emit("run.stopped", rule="budget:cost_usd", reason=exc.result or "")


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
    violations: int = 0
    session_id: str | None = None
    resume_session: str | None = None  # set when this run continues an earlier one
    cost_before: float = 0.0  # what the session had cost before this run; the harness reports session totals

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.cfg.name, "principal": self.principal,
            "status": self.status.value, "created_at": self.created_at,
            "turns": self.turns, "cost_usd": self.cost_usd, "violations": self.violations,
            "result": self.result, "error": self.error,
        }

    def record_decision(self, tool: str, tool_input: dict, decision: Decision) -> None:
        """Every gate decision is an event and a signed record; every denial is also a violation."""
        evidence = self.evidence.record(self.cfg.name, self.id, self.cfg.policy.version, tool, tool_input, decision)
        self.log.emit("policy.decision", tool=tool, rule=decision.rule, allow=decision.allow,
                      args_digest=args_digest(tool_input), evidence=evidence)
        if evidence is None:
            self.violations += 1
            self.log.emit("violation", severity="high", rule="evidence:no_receipt", tool=tool,
                          reason="the decision was made and no signed receipt was written for it",
                          args_digest=args_digest(tool_input), policy_version=self.cfg.policy.version)
        if not decision.allow:
            self.violations += 1
            self.log.emit("violation", severity=decision.severity, rule=decision.rule, tool=tool,
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

    def reopen(self, iid: str, cfg: AgentConfig, principal: str = "local") -> Instance:
        """An existing instance made runnable again: same id, same folder, same log, the harness session restored.

        The budget counters start fresh. The taint does not: if an earlier run consumed untrusted
        output, this run's gate starts tainted.
        """
        root = self.base / iid
        if not (root / "work").is_dir():
            raise FileNotFoundError(f"no instance {iid} under {self.base}")
        session = session_of(root)
        if session is None:
            raise RuntimeError(f"instance {iid} has no harness session to resume")
        inst = Instance(iid, cfg, principal, root, EventLog(root / "events.jsonl", iid), self.evidence,
                        resume_session=session, cost_before=session_cost_of(root))
        inst.log.emit("instance.resumed", definition=digest(cfg), principal=principal, session_id=session)
        self.evidence.lifecycle(iid, "instance.resume", agent=cfg.name, definition=digest(cfg),
                                policy_version=cfg.policy.version, model=cfg.model, principal=principal,
                                session_id=session)
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
            await bounded(run_loop(inst), inst.cfg.timeout_s, human.attached())
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
                                cost_usd=inst.cost_usd, violations=inst.violations, error=inst.error)


async def bounded(coro, timeout_s: float, person=None):
    """Like wait_for, except that time the person spent answering does not count against the timeout."""
    task = asyncio.ensure_future(coro)
    started = time.monotonic()
    try:
        while True:
            waited = person.waited if person is not None else 0.0
            remaining = timeout_s - (time.monotonic() - started - waited)
            if remaining <= 0:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise asyncio.TimeoutError
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if done:
                return task.result()
    except asyncio.CancelledError:
        task.cancel()
        raise


async def run_loop(inst: Instance) -> None:
    """One pass of the agent loop for this instance, every step printed, logged and traced."""
    cfg, log = inst.cfg, inst.log
    preflight(cfg)
    tr = trace.get_tracer("mainsheet")
    gate = Gate(cfg.policy, human=human.attached())
    if inst.resume_session:
        gate.tainted = tainted_before(inst.root, cfg.policy)
    options = build_options(cfg, inst.root / "work", hooks=make_hooks(gate, inst.record_decision),
                            resume=inst.resume_session)
    prompt = RESUME_PROMPT if inst.resume_session else cfg.task
    open_tools: dict[str, trace.Span] = {}
    with tr.start_as_current_span("invoke_agent") as run:
        run.set_attribute("gen_ai.operation.name", "invoke_agent")
        run.set_attribute("gen_ai.agent.name", cfg.name)
        run.set_attribute("gen_ai.request.model", cfg.model)
        run.set_attribute("mainsheet.instance", inst.id)
        run.set_attribute("mainsheet.principal", inst.principal)
        billed_to = credential()
        print(f"[{inst.id}] credential: {billed_to}")
        log.emit("run.started", task=prompt, model=cfg.model, principal=inst.principal, credential=billed_to,
                 resumed=inst.resume_session, tainted=gate.tainted)
        async for message in messages(prompt, options, log):
            if isinstance(message, SystemMessage) and message.subtype == "init":
                inst.session_id = message.data.get("session_id")
                log.emit("session", session_id=inst.session_id)
            elif isinstance(message, AssistantMessage):
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
                session_cost = getattr(message, "total_cost_usd", None)
                inst.cost_usd = None if session_cost is None else round(session_cost - inst.cost_before, 6)
                inst.result = message.result
                inst.session_id = getattr(message, "session_id", None) or inst.session_id
                cap = cfg.policy.budgets.max_cost_usd
                if stopped_at_cap(message):
                    inst.violations += 1
                    log.emit("violation", severity="medium", rule="budget:cost_usd", tool="",
                             reason=f"run stopped by the harness: cost {inst.cost_usd or 0:.4f} reached the cap of {cap}",
                             policy_version=cfg.policy.version)
                elif inst.cost_usd is not None and inst.cost_usd > cap:
                    inst.violations += 1
                    log.emit("violation", severity="medium", rule="budget:cost_usd", tool="",
                             reason=f"run cost {inst.cost_usd:.4f} exceeded {cap} without a harness stop",
                             policy_version=cfg.policy.version)
                usage = getattr(message, "usage", None) or {}
                run.set_attribute("gen_ai.usage.input_tokens", usage.get("input_tokens", 0))
                run.set_attribute("gen_ai.usage.output_tokens", usage.get("output_tokens", 0))
                run.set_attribute("mainsheet.cost_usd", inst.cost_usd or 0.0)
                run.set_attribute("mainsheet.turns", inst.turns)
                print(f"\n[{inst.id}] result: {message.result}\nturns: {inst.turns}  cost_usd: {inst.cost_usd}"
                      + (f"  session_cost_usd: {session_cost}" if inst.resume_session else ""))
                log.emit("run.ended", result=message.result, turns=inst.turns, cost_usd=inst.cost_usd,
                         session_cost_usd=session_cost, usage=usage, session_id=inst.session_id)
