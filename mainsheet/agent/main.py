"""Command line entry: run one instance of the agent defined in agent.yaml."""
import asyncio
import sys
from pathlib import Path

from mainsheet.agent.config import load
from mainsheet.agent.runtime import Registry, Status
from mainsheet.agent.telemetry import shutdown, tracer
from mainsheet.paths import default_agent

CONFIG = default_agent()


async def main(config: Path = CONFIG) -> int:
    tracer()
    registry = Registry()
    inst = registry.create(load(config))
    registry.start(inst.id)
    await inst.task
    if inst.status is not Status.finished:
        print(f"[{inst.id}] {inst.status.value}: {inst.error}", file=sys.stderr)
        return 1
    return 0


USAGE = "usage: mainsheet [agent.yaml]\n\nRun one instance of the agent the file defines. Without a file: agent.yaml in the working folder, else the example that ships with the package."


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        return
    config = Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG
    try:
        raise SystemExit(asyncio.run(main(config)))
    finally:
        shutdown()


if __name__ == "__main__":
    cli()
