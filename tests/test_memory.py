"""One store shared by every agent: entries carry source, hash, author and time, and recall finds them."""
import pytest

from mainsheet.agent.tools import memory
from mainsheet.agent.tools.memory import Store, content_hash


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MAINSHEET_MEMORY", str(tmp_path / "memory.db"))
    return Store(memory.store_path())


def test_an_entry_keeps_its_provenance(store):
    entry_id = store.remember("kbv gp count", "55,778 GPs in 2025", "https://kbv.de/x", "reader-1", content="page text")
    entry = store.recall("kbv")[0]
    assert entry["id"] == entry_id
    assert entry["source"] == "https://kbv.de/x" and entry["agent"] == "reader-1"
    assert entry["content_hash"] == content_hash("page text")
    assert entry["created"] > 0


def test_the_hash_falls_back_to_the_digest_when_no_content_is_given(store):
    store.remember("k", "the digest", "s", "a")
    assert store.recall("k")[0]["content_hash"] == content_hash("the digest")


def test_recall_searches_key_source_and_digest_newest_first(store):
    store.remember("lab budget", "1.60 to 3.80 EUR per case", "https://kvhb.de", "a")
    store.remember("epa", "PDF/A only", "https://kbv.de/epa", "b")
    assert [e["key"] for e in store.recall("kbv")] == ["epa"]
    assert [e["key"] for e in store.recall("per case")] == ["lab budget"]
    assert [e["key"] for e in store.recall("")] == ["epa", "lab budget"]
    assert store.recall("nothing") == []


def test_two_agents_share_one_store_and_list_sees_both(store):
    Store(memory.store_path()).remember("k1", "d", "s", "agent-a")
    Store(memory.store_path()).remember("k2", "d", "s", "agent-b")
    listed = store.list()
    assert {e["agent"] for e in listed} == {"agent-a", "agent-b"}
    assert "digest" not in listed[0]


def test_cleanup_forgets_one_agent_only(store):
    store.remember("k1", "d", "s", "agent-a")
    store.remember("k2", "d", "s", "agent-b")
    memory.cleanup("agent-a")
    assert [e["agent"] for e in store.list()] == ["agent-b"]
    assert "k2" in memory.artifact("agent-b") and memory.artifact("agent-a") == ""


def test_the_tools_are_three_and_two_are_read_only(store):
    tools = {t.name: t for t in memory.make_tools("agent-a")}
    assert set(tools) == {"memory_remember", "memory_recall", "memory_list"}
    assert tools["memory_recall"].annotations.read_only_hint and tools["memory_list"].annotations.read_only_hint
    assert tools["memory_remember"].annotations is None
