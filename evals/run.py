"""Run an eval suite: plant each fixture, run the agent several times, check behaviour, output and quality."""
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from agent.config import load
from agent.runtime import Registry, Status
from agent.telemetry import shutdown, tracer
from evals.cases import Case, Suite, load_suite

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "evals" / "baseline.jsonl"


def adapters(cfg):
    return [importlib.import_module(spec.module) for spec in cfg.tools.servers.values()]


async def judge(rubric: str, output: str) -> bool:
    prompt = f"Rubric: {rubric}\n\nOutput to grade:\n{output}\n\nAnswer PASS or FAIL and nothing else."
    options = ClaudeAgentOptions(tools=[], allowed_tools=[], max_turns=1, model="claude-haiku-4-5-20251001",
                                 system_prompt="You are a strict grader. Reply with PASS or FAIL only.")
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            return (message.result or "").strip().upper().startswith("PASS")
    return False


async def run_case(cfg, case: Case) -> dict:
    mods = adapters(cfg)
    passes, details = 0, []
    for _ in range(case.runs):
        for m in mods:
            if hasattr(m, "fixture"):
                m.fixture(cfg.name, case.fixture)
        run_cfg = cfg.model_copy(update={"task": case.task}) if case.task else cfg
        registry = Registry()
        inst = registry.create(run_cfg, principal="evals")
        registry.start(inst.id)
        await inst.task
        for m in mods:
            if hasattr(m, "cleanup"):
                m.cleanup(cfg.name)
        events = [json.loads(l) for l in inst.log.path.read_text().splitlines()]
        attempted = [e["tool"].split("__")[-1] for e in events if e["kind"] == "policy.decision"]
        called = [e["tool"].split("__")[-1] for e in events if e["kind"] == "policy.decision" and e["allow"]]
        output = " ".join(m.artifact(cfg.name) for m in mods if hasattr(m, "artifact")) + " " + (inst.result or "")
        failures = []
        b, o = case.behaviour, case.output
        if b.tools_called is not None and called != b.tools_called:
            failures.append(f"tools executed {called} != {b.tools_called}")
        for t in b.tools_not_called:
            if t in called:
                failures.append(f"executed forbidden {t}")
        if b.error_includes and b.error_includes.lower() not in (inst.error or "").lower():
            failures.append(f"error {inst.error!r} lacks {b.error_includes!r}")
        if inst.incidents < b.incidents_min or (b.incidents_max is not None and inst.incidents > b.incidents_max):
            failures.append(f"incidents {inst.incidents} outside [{b.incidents_min}, {b.incidents_max}]")
        if b.max_turns is not None and inst.turns > b.max_turns:
            failures.append(f"turns {inst.turns} > {b.max_turns}")
        for s in o.must_include:
            if s.lower() not in output.lower():
                failures.append(f"missing {s!r}")
        for s in o.must_not_include:
            if s.lower() in output.lower():
                failures.append(f"contains {s!r}")
        if case.judge and not failures and not await judge(case.judge, output):
            failures.append("judge: FAIL")
        if inst.status is not Status.finished and not b.error_includes:
            failures.append(f"status {inst.status.value}: {inst.error}")
        passes += not failures
        details.append({"failures": failures, "turns": inst.turns, "cost_usd": inst.cost_usd, "incidents": inst.incidents,
                        "attempted": attempted, "executed": called})
    rate = passes / case.runs
    return {"case": case.name, "category": case.category, "pass_rate": rate, "passed": rate >= case.pass_rate, "runs": details}


async def main(suite_path: Path) -> int:
    suite = load_suite(suite_path)
    cfg = load(ROOT / "agents" / f"{suite.agent}.yaml") if (ROOT / "agents" / f"{suite.agent}.yaml").exists() else load(ROOT / "agent.yaml")
    tracer()
    results = [await run_case(cfg, c) for c in suite.cases]
    row = {"ts": time.time(), "agent": suite.agent, "model": cfg.model, "policy_version": cfg.policy.version,
           "cases": len(results), "passed": sum(r["passed"] for r in results),
           "cost_usd": sum((d["cost_usd"] or 0) for r in results for d in r["runs"]), "results": results}
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    with BASELINE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    for r in results:
        mark = "pass" if r["passed"] else "FAIL"
        print(f"{mark:4} {r['category']:15} {r['case']:32} {r['pass_rate']:.2f}")
    print(f"\n{row['passed']}/{row['cases']} cases  cost ${row['cost_usd']:.3f}")
    return 0 if row["passed"] == row["cases"] else 1


def cli() -> None:
    try:
        raise SystemExit(asyncio.run(main(Path(sys.argv[1]))))
    finally:
        shutdown()


if __name__ == "__main__":
    cli()
