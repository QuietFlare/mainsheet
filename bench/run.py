"""Run one arm of the sharing benchmark: N instances of one definition at once, then one table from their logs.

    .venv/bin/python bench/run.py bench/arm_b.yaml --agents 3

The definition's task may use {questions}, {index}, {count} and {mine}. Questions come from
questions.md beside the definition and are dealt out in order, two per agent. Arm B's memory store
is a fresh file per run, so every arm starts from nothing. Every number in the table is read back
from the instances' event logs; nothing is estimated.
"""
import asyncio
import os
import sys
import time
from collections import Counter
from pathlib import Path

from mainsheet.agent.config import AgentConfig, load
from mainsheet.agent.runtime import Registry, Status, events_of
from mainsheet.agent.telemetry import shutdown, tracer
from mainsheet.paths import HOME

RESULTS = HOME / "bench" / "results"


def deal(total: int, agents: int) -> list[list[int]]:
    """Question numbers 1..total split in order across the agents, as evenly as possible."""
    per, extra = divmod(total, agents)
    groups, start = [], 1
    for i in range(agents):
        size = per + (1 if i < extra else 0)
        groups.append(list(range(start, start + size)))
        start += size
    return groups


def definitions(template: AgentConfig, questions: str, agents: int) -> list[AgentConfig]:
    numbered = sum(1 for line in questions.splitlines() if line[:1].isdigit())
    groups = deal(numbered, agents)
    return [template.model_copy(update={
        "name": f"{template.name}-{i + 1}",
        "task": template.task.format(questions=questions, index=i + 1, count=agents,
                                     mine=" and ".join(str(q) for q in groups[i])),
    }) for i in range(agents)]


def summarise(root: Path) -> dict:
    """One row from one instance's log."""
    events = events_of(root)
    kinds = Counter(e["kind"] for e in events)
    tools = Counter(e["name"].split("__")[-1] for e in events if e["kind"] == "tool.called")
    started = next((e["ts"] for e in events if e["kind"] == "run.started"), None)
    ended = next((e for e in reversed(events) if e["kind"] == "run.ended"), {})
    usage = ended.get("usage") or {}
    return {
        "instance": root.name,
        "seconds": round(ended.get("ts", 0) - started, 1) if started and ended else None,
        "calls": sum(tools.values()),
        "fetches": tools.get("WebFetch", 0) + tools.get("WebSearch", 0),
        "recalls": tools.get("memory_recall", 0) + tools.get("memory_list", 0),
        "remembers": tools.get("memory_remember", 0),
        "input": usage.get("input_tokens", 0),
        "cache_write": usage.get("cache_creation_input_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "output": usage.get("output_tokens", 0),
        "usd": ended.get("cost_usd"),
        "violations": kinds.get("violation", 0),
    }


COLUMNS = ["instance", "seconds", "calls", "fetches", "recalls", "remembers",
           "input", "cache_write", "cache_read", "output", "usd", "violations"]


def table(rows: list[dict]) -> str:
    total = {c: sum(r[c] or 0 for r in rows) if c != "instance" else "total" for c in COLUMNS}
    total["seconds"] = max((r["seconds"] or 0) for r in rows)  # wall time is the longest agent, not the sum
    total["usd"] = round(total["usd"], 4)
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in rows + [total]:
        lines.append("| " + " | ".join(str(r[c]) for c in COLUMNS) + " |")
    return "\n".join(lines)


async def run(definition: Path, agents: int) -> int:
    tracer()
    template = load(definition)
    questions = (definition.parent / "questions.md").read_text()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if any(spec.module == "mainsheet.agent.tools.memory" for spec in template.tools.servers.values()):
        os.environ["MAINSHEET_MEMORY"] = str(RESULTS / f"{template.name}-{stamp}.memory.db")
    registry = Registry()
    instances = [registry.create(cfg) for cfg in definitions(template, questions, agents)]
    for inst in instances:
        registry.start(inst.id)
    await asyncio.gather(*(inst.task for inst in instances))
    rows = [summarise(inst.root) for inst in instances]
    report = f"# {template.name}, {agents} agents, {stamp}\n\n{table(rows)}\n"
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{template.name}-{stamp}.md"
    out.write_text(report)
    print(f"\n{report}\nwritten to {out}")
    return 0 if all(inst.status is Status.finished for inst in instances) else 1


def cli() -> None:
    args = sys.argv[1:]
    agents = 3
    if "--agents" in args:
        at = args.index("--agents")
        agents = int(args[at + 1])
        del args[at:at + 2]
    if len(args) != 1:
        raise SystemExit("usage: python bench/run.py <definition.yaml> [--agents N]")
    try:
        raise SystemExit(asyncio.run(run(Path(args[0]), agents)))
    finally:
        shutdown()


if __name__ == "__main__":
    cli()
