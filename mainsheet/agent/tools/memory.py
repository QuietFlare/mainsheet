"""Shared memory bound to one agent: every instance that names this module reads and writes one store.

An entry is a digest of something read, with where it came from, a hash of what was read, which agent
wrote it and when. The store is one SQLite file, MAINSHEET_MEMORY or memory.db in the working folder,
so several instances running at once share it. The gate decides who may remember and recall; this
module only keeps the entries.
"""
import asyncio
import hashlib
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool, ToolAnnotations, create_sdk_mcp_server, tool

from mainsheet.paths import HOME

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL,
    digest TEXT NOT NULL,
    source TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    agent TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS memory_key ON memory(key);
"""


def store_path() -> Path:
    return Path(os.environ.get("MAINSHEET_MEMORY") or HOME / "memory.db")


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


class Store:
    """The entries, without any tool or agent around them. Tests use this directly."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def remember(self, key: str, digest: str, source: str, agent: str, content: str | None = None) -> int:
        """Store one entry. The hash is of the content when given, else of the digest."""
        with self._db() as db:
            cur = db.execute(
                "INSERT INTO memory(key, digest, source, content_hash, agent, created) VALUES (?,?,?,?,?,?)",
                (key, digest, source, content_hash(content if content is not None else digest), agent, time.time()))
            return cur.lastrowid

    def recall(self, query: str, limit: int = 10) -> list[dict]:
        """Entries whose key, source or digest contains the query, newest first."""
        like = f"%{query}%"
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM memory WHERE key LIKE ? OR source LIKE ? OR digest LIKE ? ORDER BY created DESC LIMIT ?",
                (like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def list(self) -> list[dict]:
        """Every key with its source, author and time, newest first, without the digests."""
        with self._db() as db:
            rows = db.execute("SELECT id, key, source, agent, created FROM memory ORDER BY created DESC").fetchall()
        return [dict(r) for r in rows]

    def forget_agent(self, agent: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM memory WHERE agent = ?", (agent,))


def _render(entry: dict) -> str:
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(entry["created"]))
    head = f"[{entry['id']}] {entry['key']}  source={entry['source']}  by={entry['agent']}  at={when}"
    if "digest" in entry:
        return f"{head}  hash={entry['content_hash']}\n{entry['digest']}"
    return head


# The evals harness calls these by name, as it does for notes.
FIXTURE_FIELDS: list[str] = []


def fixture(agent: str, fields: dict[str, str]) -> None:
    Store(store_path())


def cleanup(agent: str) -> None:
    """Remove what this agent remembered. Other agents' entries stay."""
    if store_path().exists():
        Store(store_path()).forget_agent(agent)


def artifact(agent: str) -> str:
    """Everything this agent remembered, for output assertions."""
    if not store_path().exists():
        return ""
    entries = [e for e in Store(store_path()).recall("", limit=1000) if e["agent"] == agent]
    return "\n".join(_render(e) for e in entries)


def make_tools(agent: str) -> list[SdkMcpTool]:
    store = Store(store_path())

    @tool(
        "memory_remember",
        "Store a digest of something you read so other agents need not read it again. "
        "key: a short topic or the URL. digest: the facts, with numbers. source: the URL or document. "
        "content: optionally the raw text you read, used only to hash it.",
        {"key": str, "digest": str, "source": str, "content": str},
    )
    async def memory_remember(args: dict[str, Any]) -> dict[str, Any]:
        entry_id = await asyncio.to_thread(
            store.remember, args["key"], args["digest"], args["source"], agent, args.get("content") or None)
        return {"content": [{"type": "text", "text": f"remembered [{entry_id}] {args['key']}"}]}

    @tool(
        "memory_recall",
        "Before fetching anything, ask the shared memory. Returns entries whose key, source or digest "
        "contains the query, newest first, each with source, author, time and content hash.",
        {"query": str},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def memory_recall(args: dict[str, Any]) -> dict[str, Any]:
        entries = await asyncio.to_thread(store.recall, args["query"])
        text = "\n\n".join(_render(e) for e in entries) or f"nothing remembered about {args['query']!r}"
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "memory_list",
        "Every key in the shared memory with its source and author, newest first. No digests.",
        {},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def memory_list(args: dict[str, Any]) -> dict[str, Any]:
        entries = await asyncio.to_thread(store.list)
        text = "\n".join(_render(e) for e in entries) or "memory is empty"
        return {"content": [{"type": "text", "text": text}]}

    return [memory_remember, memory_recall, memory_list]


def make_server(agent: str) -> dict:
    return create_sdk_mcp_server(name="memory", version="1.0.0", tools=make_tools(agent))
