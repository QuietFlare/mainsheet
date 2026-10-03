"""Record one event at each step: a JSON line on disk and an event on the current span."""
import json
import time
from pathlib import Path

from opentelemetry import trace


class EventLog:
    def __init__(self, path: Path, instance: str) -> None:
        self.path = path
        self.instance = instance
        path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, kind: str, **fields) -> None:
        record = {"ts": time.time(), "instance": self.instance, "kind": kind, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
        trace.get_current_span().add_event(
            kind,
            {k: v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str)
             for k, v in fields.items()},
        )
