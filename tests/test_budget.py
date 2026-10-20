"""The cost cap stops the run inside the harness, and the stop is recorded rather than raised."""
import asyncio
from types import SimpleNamespace

import pytest
from claude_agent_sdk import ResultError

from mainsheet.agent.config import AgentConfig, build_options
from mainsheet.agent.events import EventLog
from mainsheet.agent.runtime import BUDGET_STOP, messages, stopped_at_cap


def agent(cap: float) -> AgentConfig:
    return AgentConfig.model_validate({
        "name": "capped", "model": "claude-sonnet-5-5", "max_turns": 3,
        "system_prompt": "s", "task": "t", "tools": {"builtin": [], "servers": {}},
        "policy": {"budgets": {"max_cost_usd": cap}},
    })


def stream_that_stops(subtype: str):
    async def stream(prompt, options):
        yield "first"
        raise ResultError("exit 1", {"subtype": subtype, "result": "cap reached"})
    return stream


def test_the_cost_cap_is_handed_to_the_harness(tmp_path):
    assert build_options(agent(2.0), tmp_path).max_budget_usd == 2.0


def test_a_result_on_the_cap_is_recognised():
    assert stopped_at_cap(SimpleNamespace(subtype=BUDGET_STOP))
    assert not stopped_at_cap(SimpleNamespace(subtype="success"))
    assert stopped_at_cap(ResultError("x", {"subtype": BUDGET_STOP}))


def test_a_cap_stop_ends_the_stream_and_is_logged(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", "i")

    async def collect():
        return [m async for m in messages("t", None, log, stream=stream_that_stops(BUDGET_STOP))]

    assert asyncio.run(collect()) == ["first"]
    assert '"run.stopped"' in (tmp_path / "events.jsonl").read_text()


def test_any_other_error_result_still_raises(tmp_path):
    log = EventLog(tmp_path / "events.jsonl", "i")

    async def collect():
        return [m async for m in messages("t", None, log, stream=stream_that_stops("error_max_turns"))]

    with pytest.raises(ResultError):
        asyncio.run(collect())
