"""The system: which agent definitions exist, where they sit on the canvas, and how they connect."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from agent.config import AgentConfig, load, save

ROOT = Path(__file__).resolve().parent.parent
SYSTEM = ROOT / "system.yaml"
AGENTS = ROOT / "agents"
TEMPLATE = ROOT / "agent.yaml"


class AgentRef(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    x: float = 0
    y: float = 0

    @property
    def file(self) -> Path:
        return AGENTS / f"{self.name}.yaml"


class Edge(BaseModel):
    source: str
    target: str
    kind: Literal["delegates"] = "delegates"


class SystemConfig(BaseModel):
    agents: list[AgentRef] = []
    edges: list[Edge] = []

    @model_validator(mode="after")
    def _consistent(self) -> "SystemConfig":
        names = [a.name for a in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agent names must be unique")
        for e in self.edges:
            if e.source == e.target:
                raise ValueError(f"{e.source} cannot delegate to itself")
            for end in (e.source, e.target):
                if end not in names:
                    raise ValueError(f"edge refers to unknown agent {end!r}")
        return self


def load_system() -> SystemConfig:
    if not SYSTEM.exists():
        return SystemConfig()
    with SYSTEM.open() as f:
        return SystemConfig.model_validate(yaml.safe_load(f) or {})


def save_system(system: SystemConfig) -> None:
    SYSTEM.write_text(yaml.safe_dump(system.model_dump(), sort_keys=False))


def create_agent(name: str, x: float = 0, y: float = 0) -> AgentConfig:
    """Add an agent to the system with a definition copied from the template."""
    system = load_system()
    if any(a.name == name for a in system.agents):
        raise ValueError(f"agent {name!r} already exists")
    ref = AgentRef(name=name, x=x, y=y)
    cfg = load(TEMPLATE).model_copy(update={"name": name})
    save(cfg, ref.file)
    system.agents.append(ref)
    save_system(system)
    return cfg


def delete_agent(name: str) -> None:
    """Remove an agent, its definition, and every edge that touches it."""
    system = load_system()
    system.agents = [a for a in system.agents if a.name != name]
    system.edges = [e for e in system.edges if name not in (e.source, e.target)]
    save_system(system)
    (AGENTS / f"{name}.yaml").unlink(missing_ok=True)


def agent_config(name: str) -> AgentConfig:
    return load(AGENTS / f"{name}.yaml")


def update_agent(name: str, cfg: AgentConfig) -> AgentConfig:
    if cfg.name != name:
        raise ValueError("rename is not supported; delete and create instead")
    save(cfg, AGENTS / f"{name}.yaml")
    return cfg
