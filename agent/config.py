"""Load and validate an agent definition, and build the SDK options for one instance of it."""
import importlib
from pathlib import Path
from typing import Literal

import yaml
from claude_agent_sdk import ClaudeAgentOptions
from pydantic import BaseModel, Field

from agent.policy import Policy

Model = Literal[
    "claude-fable-5-1",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
]


class ServerConfig(BaseModel):
    module: str
    allow: list[str] = Field(min_length=1)


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


def preflight(cfg: AgentConfig) -> None:
    """Run every tool module's preflight, if it has one, before any model call."""
    for spec in cfg.tools.servers.values():
        check = getattr(importlib.import_module(spec.module), "preflight", None)
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
        servers[key] = importlib.import_module(spec.module).make_server(cfg.name)
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
