"""What a server offers, asked the way a client asks: one started by command is spoken to over MCP."""
import importlib
import json
import os
import subprocess

from mainsheet.agent.config import ServerConfig, stdio

HANDSHAKE = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "mainsheet", "version": "0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
]


def list_tools(server: dict, timeout: float = 30) -> list[dict]:
    """Start a stdio server, do the handshake, and return what tools/list says."""
    asked = "".join(json.dumps(message) + "\n" for message in HANDSHAKE)
    ran = subprocess.run([server["command"], *server.get("args", [])], input=asked,
                         capture_output=True, text=True, timeout=timeout,
                         env={**os.environ, **server.get("env", {})})
    for line in ran.stdout.splitlines():
        try:
            answer = json.loads(line)
        except ValueError:
            continue
        if isinstance(answer, dict) and answer.get("id") == 2:
            if "error" in answer:
                raise RuntimeError(f"{server['command']}: {answer['error'].get('message')}")
            return answer["result"]["tools"]
    said = (ran.stderr or ran.stdout).strip().splitlines()[-1:] or ["nothing"]
    raise RuntimeError(f"{server['command']} did not answer tools/list; it said: {said[0][:300]}")


def tools_of(spec: ServerConfig, agent: str = "preview") -> list[dict]:
    """[{name, description}] for one server, whichever way it is provided."""
    if spec.command:
        return [{"name": t["name"], "description": t.get("description", "")}
                for t in list_tools(stdio(spec))]
    module = importlib.import_module(spec.module)
    return [{"name": t.name, "description": t.description} for t in module.make_tools(agent)]
