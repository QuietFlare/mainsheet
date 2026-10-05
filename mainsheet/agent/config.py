"""Load and validate an agent definition, and build the SDK options for one instance of it."""
import hashlib
import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Literal

import yaml
from claude_agent_sdk import ClaudeAgentOptions
from pydantic import BaseModel, Field, model_validator

from mainsheet.agent.policy import Policy

Model = Literal[
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
]


class ServerConfig(BaseModel):
    """Where a server's tools come from: a Python module Mainsheet imports, or a program it starts and speaks MCP to."""
    module: str | None = None
    command: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    allow: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def one_source(self) -> "ServerConfig":
        if bool(self.module) == bool(self.command):
            raise ValueError("a server names either a module or a command, not both and not neither")
        return self


VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expanded(text: str) -> str:
    """${NAME} from the environment, ${NAME:-default} when it may be unset. MAINSHEET_PYTHON is this interpreter."""
    values = {**os.environ, "MAINSHEET_PYTHON": sys.executable}

    def one(found: re.Match) -> str:
        name, default = found.group(1), found.group(2)
        if name in values:
            return values[name]
        if default is not None:
            return default
        raise ValueError(f"{name} is not set, and the definition gives it no default")
    return VARIABLE.sub(one, text)


def stdio(spec: ServerConfig) -> dict:
    """The SDK's description of a server started by command. An env entry that expands to nothing is left out."""
    env = {name: expanded(value) for name, value in spec.env.items()}
    return {"type": "stdio", "command": expanded(spec.command), "args": [expanded(a) for a in spec.args],
            "env": {name: value for name, value in env.items() if value}}


class ToolsConfig(BaseModel):
    builtin: list[str] = []
    servers: dict[str, ServerConfig] = {}


class AgentConfig(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    model: Model
    max_turns: int = Field(ge=1, le=50)
    timeout_s: int = Field(default=300, ge=10, le=3600)
    permission_mode: Literal["default", "acceptEdits", "plan"] = "acceptEdits"
    system_prompt: str
    task: str
    tools: ToolsConfig
    policy: Policy = Policy()


def load(path: Path) -> AgentConfig:
    with path.open() as f:
        return AgentConfig.model_validate(yaml.safe_load(f))


def save(cfg: AgentConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False, allow_unicode=True))


def digest(cfg: AgentConfig) -> str:
    """Fingerprint of the whole definition: any change to it, with or without a new policy version, changes this."""
    return "sha256:" + hashlib.sha256(json.dumps(cfg.model_dump(), sort_keys=True).encode()).hexdigest()


# What the harness authenticates with, in the order it looks. A stored login is what is left
# when none of these is set.
CREDENTIALS = [
    ("CLAUDE_CODE_USE_BEDROCK", "Amazon Bedrock"),
    ("CLAUDE_CODE_USE_VERTEX", "Google Vertex AI"),
    ("CLAUDE_CODE_USE_FOUNDRY", "Microsoft Foundry"),
    ("ANTHROPIC_AUTH_TOKEN", "bearer token"),
    ("ANTHROPIC_API_KEY", "API key"),
    ("CLAUDE_CODE_OAUTH_TOKEN", "long-lived subscription token"),
]


def credential() -> str:
    """Name the credential a run will bill to, from the environment alone. Never the value."""
    for variable, label in CREDENTIALS:
        if os.environ.get(variable):
            return f"{label} ({variable})"
    return "stored Claude login"


def preflight(cfg: AgentConfig) -> None:
    """Run every tool module's preflight, if it has one, before any model call."""
    for spec in cfg.tools.servers.values():
        check = getattr(importlib.import_module(spec.module), "preflight", None) if spec.module else None
        if check:
            check(cfg.name)


def sandbox_settings(policy: Policy) -> dict:
    """The harness sandbox for every command the agent runs: always on, no opt-out, egress only to policy.network.allow."""
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,
        "excludedCommands": [],
        "network": {"allowedDomains": list(policy.network.allow)},
    }


def build_options(cfg: AgentConfig, cwd: Path, hooks: dict | None = None) -> ClaudeAgentOptions:
    servers = {}
    allowed = list(cfg.tools.builtin)
    for key, spec in cfg.tools.servers.items():
        servers[key] = stdio(spec) if spec.command else \
            importlib.import_module(spec.module).make_server(cfg.name)
        allowed += [f"mcp__{key}__{name}" for name in spec.allow]
    return ClaudeAgentOptions(
        cwd=str(cwd),
        model=cfg.model,
        tools=cfg.tools.builtin,
        mcp_servers=servers,
        allowed_tools=allowed,
        permission_mode=cfg.permission_mode,
        max_turns=cfg.max_turns,
        system_prompt=cfg.system_prompt,
        hooks=hooks or {},
        sandbox=sandbox_settings(cfg.policy),
    )
