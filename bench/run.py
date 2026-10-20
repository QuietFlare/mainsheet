"""Run one arm of the sharing benchmark: N instances of one definition at once, then one table from their logs.

    .venv/bin/python bench/run.py bench/arm_b.yaml --agents 3 [--stagger]

The definition's task may use {questions}, {index}, {count} and {mine}. Questions come from
questions.md beside the definition and are dealt out in order, two per agent. Arm B's memory store
is a fresh file per run, so every arm starts from nothing. With --stagger, each agent after the
first starts when the previous agent's first memory entry lands, or when that agent finishes
without writing. Every number in the table is read back from the instances' event logs; nothing
is estimated.
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


def summarise(root: Path, first_start: float | None = None) -> dict:
    """One row from one instance's log. start is seconds after the first agent of the group started."""
    events = events_of(root)
    kinds = Counter(e["kind"] for e in events)
    tools = Counter(e["name"].split("__")[-1] for e in events if e["kind"] == "tool.called")
    started = next((e["ts"] for e in events if e["kind"] == "run.started"), None)
    ended = next((e for e in reversed(events) if e["kind"] == "run.ended"), {})
    usage = ended.get("usage") or {}
    return {
        "instance": root.name,
        "start": round(started - first_start, 1) if started and first_start else 0.0,
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


COLUMNS = ["instance", "start", "seconds", "calls", "fetches", "recalls", "remembers",
           "input", "cache_write", "cache_read", "output", "usd", "violations"]


def table(rows: list[dict]) -> str:
    total = {c: sum(r[c] or 0 for r in rows) if c != "instance" else "total" for c in COLUMNS}
    total["start"] = ""
    # wall time of the group: the latest end, measured from the first start
    total["seconds"] = max(((r["start"] or 0) + (r["seconds"] or 0)) for r in rows)
    total["usd"] = round(total["usd"], 4)
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for r in rows + [total]:
        lines.append("| " + " | ".join(str(r[c]) for c in COLUMNS) + " |")
    return "\n".join(lines)


async def start_staggered(registry: Registry, instances: list) -> None:
    """Start each agent when the previous one's first memory entry lands, or when it ends without one."""
    from mainsheet.agent.tools.memory import Store, store_path
    store = Store(store_path())
    for i, inst in enumerate(instances):
        registry.start(inst.id)
        if i + 1 == len(instances):
            return
        waited = time.time()
        while not any(e["agent"] == inst.cfg.name for e in store.list()):
            if inst.task is not None and inst.task.done():
                print(f"[bench] {inst.cfg.name} ended without writing; starting the next agent anyway")
                break
            await asyncio.sleep(0.5)
        print(f"[bench] {inst.cfg.name} wrote its first entry after {time.time() - waited:.1f}s; starting the next agent")


async def run(definition: Path, agents: int, stagger: bool = False) -> int:
    tracer()
    template = load(definition)
    questions = (definition.parent / "questions.md").read_text()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shares_memory = any(spec.module == "mainsheet.agent.tools.memory" for spec in template.tools.servers.values())
    if shares_memory:
        os.environ["MAINSHEET_MEMORY"] = str(RESULTS / f"{template.name}-{stamp}.memory.db")
    if stagger and not shares_memory:
        raise SystemExit("--stagger needs a definition with the memory server; nothing to wait for otherwise")
    registry = Registry()
    instances = [registry.create(cfg) for cfg in definitions(template, questions, agents)]
    if stagger:
        await start_staggered(registry, instances)
    else:
        for inst in instances:
            registry.start(inst.id)
    await asyncio.gather(*(inst.task for inst in instances))
    first_start = min(e["ts"] for e in events_of(instances[0].root) if e["kind"] == "run.started")
    rows = [summarise(inst.root, first_start) for inst in instances]
    mode = "staggered on first memory write" if stagger else "started together"
    report = f"# {template.name}, {agents} agents, {mode}, {stamp}\n\n{table(rows)}\n"
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
    stagger = "--stagger" in args
    args = [a for a in args if a != "--stagger"]
    if len(args) != 1:
        raise SystemExit("usage: python bench/run.py <definition.yaml> [--agents N] [--stagger]")
    try:
        raise SystemExit(asyncio.run(run(Path(args[0]), agents, stagger)))
    finally:
        shutdown()


if __name__ == "__main__":
    cli()
