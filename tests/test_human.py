"""The person an agent may address: the ask_human tool, the approval path, the run clock, and skills shipped by a plugin."""
import asyncio
import json

import pytest

from mainsheet.agent.config import AgentConfig, build_options, digest
from mainsheet.agent.policy import PENDING, Gate, Policy, make_hooks
from mainsheet.agent.runtime import bounded
from mainsheet.agent.tools import human


@pytest.fixture(autouse=True)
def detached():
    human.attach(None)
    yield
    human.attach(None)


def ask(args: dict) -> dict:
    [tool] = human.make_tools("probe")
    return asyncio.run(tool.handler(args))


def test_the_tool_returns_the_persons_words():
    human.attach(human.Scripted(["Seema"]))
    result = ask({"question": "What is your name?"})
    assert result["content"][0]["text"] == "Seema" and not result.get("is_error")
    assert human.attached().questions == ["What is your name?"]


def test_the_tool_errors_when_nobody_is_attached():
    result = ask({"question": "Anyone?"})
    assert result["is_error"] and result["content"][0]["text"] == human.NOBODY


def test_an_exhausted_script_is_a_closed_terminal():
    human.attach(human.Scripted([]))
    result = ask({"question": "Still there?"})
    assert result["is_error"] and "no more answers" in result["content"][0]["text"]


def policy(**tools) -> Policy:
    return Policy.model_validate({"tools": tools, "budgets": {"max_tool_calls": 2}})


def test_approval_without_a_person_is_denied_as_before():
    d = Gate(policy(deploy={"approval": "human"})).pre("mcp__x__deploy", {"env": "prod"})
    assert not d.allow and d.rule == "approval_required"


def test_approval_with_a_person_is_pending_then_decided_by_the_answer():
    gate = Gate(policy(deploy={"approval": "human"}), human=human.Scripted(["yes", "no, not today"]))
    assert gate.pre("mcp__x__deploy", {"env": "prod"}).rule == PENDING
    allowed = gate.approved("mcp__x__deploy", {"env": "prod"}, "yes")
    assert allowed.allow and allowed.rule == "approval:human" and gate.tool_calls == 1
    refused = gate.approved("mcp__x__deploy", {"env": "test"}, "no, not today")
    assert not refused.allow and refused.rule == "approval:human" and "not today" in refused.reason
    again = gate.pre("mcp__x__deploy", {"env": "test"})
    assert again.rule == "denial_continuity"


def test_the_budget_is_checked_before_the_person_is_asked():
    gate = Gate(policy(deploy={"approval": "human"}), human=human.Scripted(["yes"]))
    gate.tool_calls = 2
    assert gate.pre("mcp__x__deploy", {}).rule == "budget:tool_calls"


def test_the_hook_puts_the_question_and_records_the_answer():
    person = human.Scripted(["yes"])
    gate = Gate(policy(deploy={"approval": "human"}), human=person)
    recorded = []
    hooks = make_hooks(gate, lambda tool, args, d: recorded.append((tool, d)))
    [pre] = hooks["PreToolUse"][0].hooks
    out = asyncio.run(pre({"tool_name": "mcp__x__deploy", "tool_input": {"env": "prod"}}, "id", None))
    assert out == {}
    assert person.questions and "deploy" in person.questions[0] and "prod" in person.questions[0]
    assert recorded == [("mcp__x__deploy", recorded[0][1])] and recorded[0][1].rule == "approval:human"


def test_a_closed_terminal_during_approval_is_a_refusal():
    gate = Gate(policy(deploy={"approval": "human"}), human=human.Scripted([]))
    hooks = make_hooks(gate, lambda *a: None)
    [pre] = hooks["PreToolUse"][0].hooks
    out = asyncio.run(pre({"tool_name": "mcp__x__deploy", "tool_input": {}}, "id", None))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no answer" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_time_waiting_on_the_person_does_not_count_against_the_timeout():
    person = human.Scripted(["x"], delay=0.3)

    async def run():
        await person.ask("?")  # 0.3 s of the person's time
        await asyncio.sleep(0.05)  # the run's own time
        return "done"

    assert asyncio.run(bounded(run(), 0.2, person)) == "done"


def test_the_run_still_times_out_on_its_own_time():
    async def run():
        await asyncio.sleep(0.5)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(bounded(run(), 0.1, human.Scripted([])))


def plugin(tmp_path, name="probe", skill="greet", body="Ask their name, then greet them."):
    folder = tmp_path / name
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))
    (folder / "skills" / skill).mkdir(parents=True)
    (folder / "skills" / skill / "SKILL.md").write_text(f"---\nname: {skill}\n---\n{body}\n")
    return folder


def agent(plugins, skills) -> dict:
    return {"name": "probe", "model": "claude-sonnet-5", "max_turns": 2, "system_prompt": "s", "task": "t",
            "tools": {"builtin": []}, "plugins": [str(p) for p in plugins], "skills": skills}


def test_a_skill_must_name_its_plugin_and_exist_there(tmp_path):
    folder = plugin(tmp_path)
    AgentConfig.model_validate(agent([folder], ["probe:greet"]))
    with pytest.raises(ValueError, match="plugin:skill"):
        AgentConfig.model_validate(agent([folder], ["greet"]))
    with pytest.raises(ValueError, match="no skill 'bye'"):
        AgentConfig.model_validate(agent([folder], ["probe:bye"]))
    with pytest.raises(ValueError, match="no plugin named 'other'"):
        AgentConfig.model_validate(agent([folder], ["other:greet"]))


def test_a_changed_skill_is_a_different_agent(tmp_path):
    folder = plugin(tmp_path)
    cfg = AgentConfig.model_validate(agent([folder], ["probe:greet"]))
    before = digest(cfg)
    (folder / "skills" / "greet" / "SKILL.md").write_text("---\nname: greet\n---\nSomething else.\n")
    assert digest(cfg) != before


def test_the_harness_gets_the_plugin_the_skill_and_the_skill_tool(tmp_path):
    folder = plugin(tmp_path)
    cfg = AgentConfig.model_validate(agent([folder], ["probe:greet"]))
    options = build_options(cfg, tmp_path)
    assert options.plugins == [{"type": "local", "path": str(folder.resolve())}]
    assert options.skills == ["probe:greet"] and "Skill" in options.tools and options.setting_sources == []


def test_an_agent_without_skills_gets_none_and_no_skill_tool(tmp_path):
    cfg = AgentConfig.model_validate(agent([], []))
    options = build_options(cfg, tmp_path)
    assert options.skills == [] and options.plugins == [] and "Skill" not in options.tools
