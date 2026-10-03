"""Evidence: each gate decision goes into Vaara's hash chain and leaves a signed receipt beside it."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from vaara.audit.decision_receipts import RECEIPTS_DIRNAME, verify_receipt_file
from vaara.audit.sqlite_backend import SQLiteAuditBackend
from vaara.audit.trail import EventType
from vaara.taxonomy.actions import UNKNOWN_ACTION, ActionRequest

from mainsheet.agent.policy import Decision, args_digest
from mainsheet.paths import HOME

TRAIL = HOME / "trail"
DB = "audit.db"


def receipt_path(root: Path, record_id: str) -> Path | None:
    """Vaara files receipts by day; the record id is the file name."""
    return next((root / RECEIPTS_DIRNAME).glob(f"*/{record_id}.json"), None)


class Evidence:
    """One trail for every instance that shares this directory. Mainsheet decides; Vaara only records."""

    def __init__(self, root: Path = TRAIL) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        # strict: a trail whose chain is already broken is refused, not appended to.
        self.trail = SQLiteAuditBackend(root / DB).load_trail(strict=True)

    def record(self, agent: str, instance: str, policy_version: int,
               tool: str, tool_input: dict, decision: Decision) -> str | None:
        """Write the request and the decision. Returns the decision's record id, or None when it has no receipt."""
        action_id = self.trail.record_action_requested(ActionRequest(
            agent_id=agent, tool_name=tool, action_type=UNKNOWN_ACTION, session_id=instance,
            context={"args_digest": args_digest(tool_input), "policy_version": policy_version}))
        # The gate works by rules, not scores, so the risk is 0 for an allow and 1 for a denial.
        self.trail.record_decision(
            action_id, agent, tool, "allow" if decision.allow else "deny",
            reason=f"{decision.rule}: {decision.reason}" if decision.reason else decision.rule,
            risk_score=0.0 if decision.allow else 1.0,
            policy_id=f"mainsheet:{agent}/{policy_version}",
            violation_type="" if decision.allow else decision.rule)
        record_id = self.trail.get_action_trail(action_id)[-1].record_id
        return record_id if receipt_path(self.root, record_id) else None

    def lifecycle(self, instance: str, step: str, **detail) -> None:
        """Write one step in an instance's life into the same chain. The actor is Mainsheet, not the agent."""
        self.trail.record_execution(instance, "mainsheet", f"mainsheet.{step}", detail)


def history(instance: str, root: Path = TRAIL) -> list[str]:
    """What the chain holds about one instance, in order: its life and its decisions. Works after it is deleted."""
    trail = SQLiteAuditBackend(root / DB).load_trail()
    hashes = {r.record_id: r.record_hash for r in trail.snapshot()}
    actions, lines = set(), []
    for r in trail.snapshot():
        when = datetime.fromtimestamp(r.timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if r.action_id == instance:
            detail = "  ".join(f"{k}={v}" for k, v in r.data.get("result_summary", {}).items() if v is not None)
            lines.append(f"{when}  {r.tool_name.removeprefix('mainsheet.')}  {detail}".rstrip())
        elif r.event_type is EventType.ACTION_REQUESTED and r.data.get("session_id") == instance:
            actions.add(r.action_id)
        elif r.action_id in actions and "decision" in r.data:
            path = receipt_path(root, r.record_id)
            signed = path is not None and verify_receipt_file(path, trail_hashes=hashes).ok
            lines.append(f"{when}  decision  {r.data['decision']}  {r.tool_name}  {r.data['reason']}"
                         f"  [{'receipt verifies' if signed else 'RECEIPT FAILS'}]")
    return lines


def verify(events: Path, root: Path = TRAIL) -> list[str]:
    """Check one run: the chain is intact and every policy.decision event names a record whose receipt verifies.

    Returns one line per decision, each starting with OK or FAIL.
    """
    if not (root / DB).exists():
        return [f"FAIL  no trail at {root / DB}"]
    trail = SQLiteAuditBackend(root / DB).load_trail()
    broken = trail.verify_chain()
    lines = [f"FAIL  chain: {broken}"] if broken else []
    hashes = {r.record_id: r.record_hash for r in trail.snapshot()}
    for line in events.read_text().splitlines():
        event = json.loads(line)
        if event["kind"] != "policy.decision":
            continue
        label = f"{'allow' if event['allow'] else 'deny':<5}  {event['tool']}  {event['rule']}"
        path = receipt_path(root, event.get("evidence") or "-")
        if path is None:
            lines.append(f"FAIL  {label}  (no receipt)")
            continue
        check = verify_receipt_file(path, trail_hashes=hashes)
        same = (check.decision == "allow") == event["allow"] and check.tool == event["tool"]
        if check.ok and same:
            lines.append(f"OK    {label}")
        else:
            lines.append(f"FAIL  {label}  ({check.detail or 'receipt and event disagree'})")
    return lines


def cli() -> None:
    """mainsheet-verify <instance id>: verify the evidence for one run, then print what the chain holds about it."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: mainsheet-verify <instance id>")
    if not (TRAIL / DB).exists():
        raise SystemExit(f"no trail at {TRAIL / DB}")
    instance = sys.argv[1]
    events = HOME / "instances" / instance / "events.jsonl"
    failed = 0
    if events.exists():
        lines = verify(events)
        failed = sum(line.startswith("FAIL") for line in lines)
        print("\n".join(lines + [f"{len(lines) - failed}/{len(lines)} verified"]))
    else:
        broken = SQLiteAuditBackend(TRAIL / DB).load_trail().verify_chain()
        failed = 1 if broken else 0
        print("no event log for this instance; the chain is all that is left of it")
        print(f"FAIL  chain: {broken}" if broken else "OK    chain intact")
    told = history(instance)
    print("\nin the chain:\n" + "\n".join(told or ["nothing"]))
    raise SystemExit(1 if failed or "RECEIPT FAILS" in "".join(told) else 0)
