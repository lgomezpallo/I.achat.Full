"""Explicit recall commands must persist without model/tool availability.

Isolated SQLite/HTTP tests, not a live-provider Oracle E2E.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import iachat.app as module
from iachat.store import ConversationStore


def test_explicit_recall_survives_unavailable_planners_and_restart(monkeypatch, tmp_path):
    path = str(tmp_path / "explicit-recall.sqlite3")
    store = ConversationStore(path)
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")

    def forbidden(*args, **kwargs):
        raise AssertionError("Explicit recall must not invoke any provider or planner")

    monkeypatch.setattr(module, "get_backend", forbidden)
    monkeypatch.setattr(module, "handle_structured_chat", forbidden)
    client = TestClient(module.app)

    first = client.post("/api/chat", json={
        "text": "Guardá que el proyecto Faro utiliza PostgreSQL.",
        "project": "Faro",
    })
    assert first.status_code == 200, first.text
    assert "Guardé" in first.json()["answer"]
    cid = first.json()["conversation_id"]

    # Repeating the request must be idempotent, even with case/whitespace changes.
    second = client.post("/api/chat", json={
        "conversation_id": cid, "project": "Faro",
        "text": "guardá que el   proyecto Faro utiliza PostgreSQL!",
    })
    assert second.status_code == 200, second.text
    assert "Ya tenía" in second.json()["answer"]

    reopened = ConversationStore(path)
    history = reopened.get(cid, "alice")
    assert len(history) == 4
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert reopened.get_summary(cid, "alice")["processed_count"] == 4
    assert [m["content"] for m in reopened.list_memories("alice", "Faro")] == [
        "el proyecto Faro utiliza PostgreSQL"
    ]
    assert reopened.list_memories("alice", "Otro") == []
    assert reopened.list_memories("bob", "Faro") == []
    assert reopened.list_automatic_memory_log("alice") == []


def test_explicit_memory_concurrent_dedup_and_project_scope(tmp_path):
    path = str(tmp_path / "explicit-concurrency.sqlite3")
    stores = [ConversationStore(path), ConversationStore(path)]

    def write(index):
        return stores[index].save_explicit_memory(
            "id-" + str(index),
            "Prefiero informes detallados.",
            owner="alice",
            project="Faro",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, (0, 1)))
    assert sorted(outcomes) == [False, True]

    reopened = ConversationStore(path)
    assert len(reopened.list_memories("alice", "Faro")) == 1
    assert reopened.list_automatic_memory_log("alice") == []
    assert reopened.save_explicit_memory(
        "id-2", "  prefiero informes detallados! ", "alice", "Faro"
    ) is False

    # Another project and another owner must remain independent.
    assert reopened.save_explicit_memory(
        "id-3", "Prefiero informes detallados.", "alice", "Otro"
    ) is True
    assert reopened.save_explicit_memory(
        "id-4", "Prefiero informes detallados.", "bob", "Faro"
    ) is True
    assert len(reopened.list_memories("alice", "Faro")) == 1
    assert len(reopened.list_memories("alice", "Otro")) == 1
    assert len(reopened.list_memories("bob", "Faro")) == 1


def test_global_explicit_memory_not_duplicated_inside_project(tmp_path):
    store = ConversationStore(str(tmp_path / "explicit-global.sqlite3"))
    assert store.save_explicit_memory("global", "Prefiero respuestas breves", "alice", "")
    assert not store.save_explicit_memory(
        "project-duplicate", "prefiero  respuestas breves!", "alice", "Faro"
    )
    assert len(store.list_memories("alice", "Faro")) == 1
