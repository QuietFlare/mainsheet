"""A server comes from a module or a command, and a command's definition expands from the environment."""
import json
import sys

import pytest
from pydantic import ValidationError

from mainsheet.agent.config import ServerConfig, expanded, stdio
from mainsheet.agent.mcp import list_tools, tools_of

# A stdio server small enough to live in a test: it answers initialize and tools/list, nothing else.
FAKE = """
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    if m.get("id") == 1:
        print(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18",
              "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}}), flush=True)
    elif m.get("id") == 2:
        print(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": [
              {"name": "fake_read", "description": "reads"}, {"name": "fake_write", "description": "writes"}]}}),
              flush=True)
"""


def test_a_server_names_a_module_or_a_command_and_not_both():
    assert ServerConfig(module="x.y", allow=["a"]).module == "x.y"
    assert ServerConfig(command="prog", args=["-x"], allow=["a"]).command == "prog"
    with pytest.raises(ValidationError):
        ServerConfig(allow=["a"])
    with pytest.raises(ValidationError):
        ServerConfig(module="x.y", command="prog", allow=["a"])


def test_variables_expand_from_the_environment_with_defaults(monkeypatch):
    monkeypatch.setenv("WORK", "/w")
    monkeypatch.delenv("ABSENT", raising=False)
    assert expanded("--dir ${WORK}/in") == "--dir /w/in"
    assert expanded("${ABSENT:-none}") == "none"
    assert expanded("${ABSENT:-}") == ""
    assert expanded("${MAINSHEET_PYTHON}") == sys.executable
    with pytest.raises(ValueError, match="ABSENT is not set"):
        expanded("${ABSENT}")


def test_a_command_server_becomes_a_stdio_description_without_empty_env(monkeypatch):
    monkeypatch.setenv("KEY", "k")
    monkeypatch.delenv("UNSET", raising=False)
    spec = ServerConfig(command="${MAINSHEET_PYTHON}", args=["-m", "serve", "${KEY}"],
                        env={"KEY": "${KEY}", "UNSET": "${UNSET:-}"}, allow=["a"])
    assert stdio(spec) == {"type": "stdio", "command": sys.executable, "args": ["-m", "serve", "k"],
                           "env": {"KEY": "k"}}


def test_tools_are_listed_by_speaking_to_the_server():
    spec = ServerConfig(command=sys.executable, args=["-c", FAKE], allow=["fake_read"])
    assert [t["name"] for t in list_tools(stdio(spec))] == ["fake_read", "fake_write"]
    assert tools_of(spec) == [{"name": "fake_read", "description": "reads"},
                              {"name": "fake_write", "description": "writes"}]


def test_a_server_that_does_not_answer_is_said():
    spec = ServerConfig(command=sys.executable, args=["-c", "print('hello')"], allow=["a"])
    with pytest.raises(RuntimeError, match="did not answer tools/list"):
        list_tools(stdio(spec))
