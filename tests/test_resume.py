"""A stopped run continues: same instance, the harness session restored, fresh budget, taint carried over."""
import json
from pathlib import Path

import pytest

from mainsheet.agent.config import AgentConfig, build_options
from mainsheet.agent.main import parse
from mainsheet.agent.policy import Policy
from mainsheet.agent.runtime import RESUME_PROMPT, Registry, session_cost_of, session_of, tainted_before


def agent() -> AgentConfig:
    return AgentConfig.model_validate({
        "name": "rs", "model": "claude-sonnet-5-5", "max_turns": 3, "system_prompt": "s", "task": "t",
        "tools": {"builtin": ["WebFetch", "Read"], "servers": {}},
        "policy": {"tools": {"WebFetch": {"untrusted_output": True}, "Read": {}}},
    })


def instance(tmp_path: Path, events: list[dict] = ()) -> Path:
    root = tmp_path / "instances" / "r-1"
    (root / "work").mkdir(parents=True)
    if events:
        (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    return root


def test_the_session_id_comes_from_the_instance_log_first(tmp_path):
    root = instance(tmp_path, [{"kind": "session", "session_id": "old"}, {"kind": "run.ended", "session_id": "new"}])
    assert session_of(root, projects=tmp_path / "none") == "new"


def test_an_older_run_is_found_through_the_harness_transcript_folder(tmp_path):
    root = instance(tmp_path)
    folder = tmp_path / "projects" / str(root / "work").replace("/", "-")
    folder.mkdir(parents=True)
    (folder / "abc123.jsonl").write_text("{}\n")
    assert session_of(root, projects=tmp_path / "projects") == "abc123"


def test_no_session_anywhere_is_none(tmp_path):
    assert session_of(instance(tmp_path), projects=tmp_path / "projects") is None


def test_taint_carries_over_from_an_earlier_run(tmp_path):
    policy = agent().policy
    assert tainted_before(instance(tmp_path, [{"kind": "tool.called", "name": "WebFetch"}]), policy)
    assert not tainted_before(instance(tmp_path / "b", [{"kind": "tool.called", "name": "Read"}]), policy)


def test_the_session_cost_so_far_comes_from_the_last_run(tmp_path):
    # The harness reports session totals. A run after this change logs the total under session_cost_usd;
    # a run before it logged only cost_usd, which was the total then. Both read back as the total.
    assert session_cost_of(instance(tmp_path, [{"kind": "run.ended", "cost_usd": 1.5, "session_cost_usd": 8.7}])) == 8.7
    assert session_cost_of(instance(tmp_path / "old", [{"kind": "run.ended", "cost_usd": 7.09}])) == 7.09
    assert session_cost_of(instance(tmp_path / "none")) == 0.0


def test_a_resumed_instance_knows_what_the_session_cost_before(tmp_path, monkeypatch):
    import mainsheet.agent.runtime as runtime
    instance(tmp_path, [{"kind": "run.ended", "session_id": "sess", "cost_usd": 7.09}])
    monkeypatch.setattr(runtime, "HARNESS_PROJECTS", tmp_path / "projects")
    inst = Registry(base=tmp_path / "instances", trail=tmp_path / "trail").reopen("r-1", agent())
    assert inst.cost_before == 7.09


def test_reopen_keeps_the_instance_and_restores_its_session(tmp_path, monkeypatch):
    import mainsheet.agent.runtime as runtime
    root = instance(tmp_path, [{"kind": "run.ended", "session_id": "sess"}])
    monkeypatch.setattr(runtime, "HARNESS_PROJECTS", tmp_path / "projects")
    registry = Registry(base=tmp_path / "instances", trail=tmp_path / "trail")
    inst = registry.reopen("r-1", agent())
    assert inst.id == "r-1" and inst.root == root and inst.resume_session == "sess"
    lines = (root / "events.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["kind"] == "instance.resumed"


def test_reopen_refuses_an_unknown_instance_or_one_without_a_session(tmp_path):
    registry = Registry(base=tmp_path / "instances", trail=tmp_path / "trail")
    with pytest.raises(FileNotFoundError):
        registry.reopen("missing", agent())
    instance(tmp_path)
    with pytest.raises(RuntimeError, match="no harness session"):
        registry.reopen("r-1", agent())


def test_the_session_is_handed_to_the_harness(tmp_path):
    assert build_options(agent(), tmp_path, resume="sess").resume == "sess"
    assert build_options(agent(), tmp_path).resume is None


def test_a_resumed_run_is_told_to_continue_not_to_start_over():
    assert "Continue" in RESUME_PROMPT and "repeat" in RESUME_PROMPT


def test_the_flag_is_parsed_with_or_without_a_config_path():
    assert parse(["a.yaml", "--resume", "r-1"]) == (Path("a.yaml"), "r-1")
    assert parse(["--resume", "r-1", "a.yaml"]) == (Path("a.yaml"), "r-1")
    assert parse(["a.yaml"])[1] is None
    with pytest.raises(SystemExit, match="needs an instance id"):
        parse(["a.yaml", "--resume"])
