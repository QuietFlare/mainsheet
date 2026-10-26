"""Verify the receipts in this folder against the issuer's public key, without the author's chain.

    pip install vaara
    python docs/paper/data/verify.py

For every policy.decision event in a run's events.jsonl, the receipt file the event names must
exist, carry a signature that verifies under the key, carry an evidence block whose digest
matches the signed reference, and bind to that event: the same record id, the same tool, the
same verdict, and a decision time within five seconds of the event's timestamp.

What a receipt does not carry. The argument digest of the call is in the event and in the
author's chain, not in the receipt, so the receipt attests the decision, the tool, the agent and
the time, and the event log attests which arguments were decided on. A receipt also says
nothing about what the tool did once allowed.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from vaara.audit.decision_receipts import verify_receipt_file

HERE = Path(__file__).resolve().parent
KEY = (HERE / "issuer-es256.pub.pem").read_bytes()
SLACK_S = 5.0


def bound(path: Path, event: dict) -> str | None:
    """The reason the receipt at path does not belong to this event, or None when it does."""
    evidence = json.loads(path.read_text())["evidence"]
    if evidence.get("recordId") != event.get("evidence"):
        return "record id differs from the event's receipt id"
    if evidence.get("toolName") != event["tool"]:
        return "tool differs"
    if (evidence.get("decision") == "allow") != bool(event["allow"]):
        return "verdict differs"
    decided = datetime.fromisoformat(evidence["decidedAt"].replace("Z", "+00:00")).timestamp()
    if abs(decided - float(event["ts"])) > SLACK_S:
        return f"decided {decided - float(event['ts']):+.1f} s from the event"
    return None


def check(run: Path) -> tuple[int, int]:
    ok = total = 0
    for line in (run / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event.get("kind") != "policy.decision":
            continue
        total += 1
        label = f"{run.name}  {event['tool']}  {event['rule']}"
        path = run / "receipts" / f"{event.get('evidence')}.json"
        if not path.exists():
            print(f"FAIL  {label}  no receipt")
            continue
        result = verify_receipt_file(path, public_key_pem=KEY)
        if not result.ok:
            print(f"FAIL  {label}  {result.detail or 'signature or evidence digest'}")
            continue
        why = bound(path, event)
        if why:
            print(f"FAIL  {label}  {why}")
            continue
        ok += 1
    return ok, total


def main() -> int:
    failed = False
    for run in sorted(p for p in HERE.iterdir() if p.is_dir()):
        ok, total = check(run)
        print(f"{run.name:8} {ok}/{total} receipts verify and bind to their events")
        failed |= ok != total
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
