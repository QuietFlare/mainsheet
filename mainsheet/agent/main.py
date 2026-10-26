"""Command line entry: run one instance of the agent defined in agent.yaml."""
import asyncio
import sys
from pathlib import Path

from mainsheet.agent.config import load
from mainsheet.agent.runtime import Registry, Status
from mainsheet.agent.telemetry import shutdown, tracer
from mainsheet.agent.tools import human
from mainsheet.paths import default_agent

CONFIG = default_agent()


async def main(config: Path = CONFIG, resume: str | None = None) -> int:
    tracer()
    human.attach(human.Terminal())  # the person is whoever started this command
    registry = Registry()
    cfg = load(config)
    inst = registry.reopen(resume, cfg) if resume else registry.create(cfg)
    registry.start(inst.id)
    await inst.task
    if inst.status is not Status.finished:
        print(f"[{inst.id}] {inst.status.value}: {inst.error}", file=sys.stderr)
        return 1
    return 0


USAGE = """usage: mainsheet [agent.yaml] [--resume <instance id>]

Run one instance of the agent the file defines. Without a file: agent.yaml in the working folder,
else the example that ships with the package.

--resume <instance id>   Continue that instance's run with a fresh budget. The harness restores its
                         conversation; the gate starts tainted if an earlier run consumed untrusted output."""


def parse(argv: list[str]) -> tuple[Path, str | None]:
    """The config path and the instance to resume, from the arguments after the program name."""
    resume = None
    rest = []
    args = iter(argv)
    for arg in args:
        if arg == "--resume":
            resume = next(args, None)
            if resume is None:
                raise SystemExit("--resume needs an instance id")
        else:
            rest.append(arg)
    if len(rest) > 1:
        raise SystemExit(USAGE)
    return (Path(rest[0]) if rest else CONFIG), resume


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("-V", "--version"):
        from importlib.metadata import version
        print(f"mainsheet {version('mainsheet')}")
        return
    config, resume = parse(sys.argv[1:])
    try:
        raise SystemExit(asyncio.run(main(config, resume)))
    finally:
        shutdown()


if __name__ == "__main__":
    cli()
