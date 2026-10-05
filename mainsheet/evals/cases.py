"""The shape of an eval case: a fixture, a run, and assertions on behaviour, output and quality."""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from mainsheet.paths import TAXONOMY



class Category(BaseModel):
    id: str
    description: str
    expect: str


class Behaviour(BaseModel):
    tools_called: list[str] | None = None
    tools_not_called: list[str] = []
    violations_min: int = 0
    violations_max: int | None = None
    max_turns: int | None = None
    error_includes: str | None = None


class Output(BaseModel):
    must_include: list[str] = []
    must_not_include: list[str] = []


class Case(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    category: str
    fixture: dict[str, str]
    task: str | None = None
    behaviour: Behaviour = Behaviour()
    output: Output = Output()
    judge: str | None = None
    runs: int = Field(default=3, ge=1, le=10)
    pass_rate: float = Field(default=0.67, ge=0, le=1)


class Suite(BaseModel):
    agent: str
    cases: list[Case]

    def uncovered(self, taxonomy: list[Category]) -> list[str]:
        have = {c.category for c in self.cases}
        return [t.id for t in taxonomy if t.id not in have]


def load_taxonomy(path: Path = TAXONOMY) -> list[Category]:
    with path.open() as f:
        return [Category.model_validate(c) for c in yaml.safe_load(f)["categories"]]


def load_suite(path: Path) -> Suite:
    with path.open() as f:
        return Suite.model_validate(yaml.safe_load(f))


def save_suite(suite: Suite, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(suite.model_dump(exclude_none=True), sort_keys=False, allow_unicode=True))
