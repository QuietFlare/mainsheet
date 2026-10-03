"""Evidence: every decision leaves a record that verifies, and a changed record does not."""
import json

import pytest

from agent.config import digest, load
from agent.events import EventLog
from agent.evidence import ROOT, Evidence, history, receipt_path, verify
from agent.policy import Decision
from agent.runtime import Registry

ALLOW = Decision(allow=True, rule="allowed")
DENY = Decision(allow=False, rule="arg:title", severity="medium", reason="title must match '^Standup'")


@pytest.fixture(autouse=True)
def vaara_home(tmp_path, monkeypatch):
    """Vaara lists every trail it writes under its home; keep that out of the real one."""
    monkeypatch.setenv("VAARA_HOME", str(tmp_path / "vaara-home"))


def run(tmp_path, decisions):
    """Record decisions the way an instance does: one Vaara record and one event each."""
    evidence = Evidence(tmp_path / "trail")
    log = EventLog(tmp_path / "events.jsonl", "standup-1")
    for decision in decisions:
        record_id = evidence.record("standup", "standup-1", 1, "mcp__notes__notes_write", {"title": "x"}, decision)
        log.emit("policy.decision", tool="mcp__notes__notes_write", rule=decision.rule, allow=decision.allow,
                 evidence=record_id)
    return log.path, evidence.root


def test_each_decision_has_a_receipt_that_verifies(tmp_path):
    events, trail = run(tmp_path, [ALLOW, DENY])
    lines = verify(events, trail)
    assert len(lines) == 2 and all(line.startswith("OK") for line in lines)


def test_a_changed_receipt_fails(tmp_path):
    events, trail = run(tmp_path, [DENY])
    path = receipt_path(trail, json.loads(events.read_text())["evidence"])
    body = json.loads(path.read_text())
    body["evidence"]["decision"] = "allow"
    path.write_text(json.dumps(body))
    assert verify(events, trail)[0].startswith("FAIL")


def test_an_event_that_claims_the_opposite_fails(tmp_path):
    events, trail = run(tmp_path, [DENY])
    event = json.loads(events.read_text())
    event["allow"] = True
    events.write_text(json.dumps(event) + "\n")
    assert verify(events, trail)[0].startswith("FAIL")


def test_a_decision_without_a_record_fails(tmp_path):
    events, trail = run(tmp_path, [ALLOW])
    event = json.loads(events.read_text())
    event["evidence"] = None
    events.write_text(json.dumps(event) + "\n")
    assert "no receipt" in verify(events, trail)[0]


def test_an_instance_leaves_its_life_in_the_chain_after_it_is_deleted(tmp_path):
    registry = Registry(base=tmp_path / "instances", trail=tmp_path / "trail")
    inst = registry.create(load(ROOT / "agents" / "egress_probe.yaml"))
    inst.record_decision("Bash", {"command": "ls"}, ALLOW)
    registry.delete(inst.id)
    assert not inst.root.exists()
    told = history(inst.id, tmp_path / "trail")
    assert "instance.create" in told[0] and digest(inst.cfg) in told[0]
    assert "decision  allow  Bash" in told[1] and "receipt verifies" in told[1]
    assert "instance.delete" in told[2]


def test_a_changed_definition_has_another_fingerprint():
    cfg = load(ROOT / "agents" / "egress_probe.yaml")
    changed = cfg.model_copy(update={"task": cfg.task + " Then run it again."})
    assert changed.policy.version == cfg.policy.version and digest(changed) != digest(cfg)


def test_a_second_writer_extends_the_same_chain(tmp_path):
    events, trail = run(tmp_path, [ALLOW])
    Evidence(trail).record("other", "other-1", 1, "Bash", {}, DENY)
    assert verify(events, trail)[0].startswith("OK")
