"""Regression: automatic memory survives failed inference and restart.

The fake backend never calls an external provider. Real Oracle E2E is separate.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import iachat.app as module
from iachat.store import ConversationStore


def _setup(monkeypatch, tmp_path):
    path = str(tmp_path / "auto-before-provider.sqlite3")
    store = ConversationStore(path)
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="skip"),
    )
    return store, path, TestClient(module.app)


def test_failed_provider_preserves_automatic_memory_and_corrections(monkeypatch, tmp_path):
    store, path, client = _setup(monkeypatch, tmp_path)

    class Unavailable:
        def answer(self, messages, images=None):
            raise RuntimeError("providers_unavailable")

    monkeypatch.setattr(module, "get_backend", lambda: Unavailable())
    first = client.post("/api/chat", json={
        "project": "Cine", "text": "Me gustan las películas de misterio.",
    })
    assert first.status_code == 503
    info = store.list_conversations("alice", "Cine")
    assert len(info) == 1
    cid = info[0]["id"]
    assert store.get(cid, "alice")[0]["content"] == "Me gustan las películas de misterio."
    assert store.list_memories("alice", "Cine")[0]["content"] == "Me gustan las películas de misterio"
    assert len(store.list_automatic_memory_log("alice")) == 1

    second = client.post("/api/chat", json={
        "conversation_id": cid, "project": "Cine",
        "text": "No me gustan las películas de misterio.",
    })
    assert second.status_code == 503
    assert len(store.get(cid, "alice")) == 2
    assert store.list_memories("alice", "Cine")[0]["content"] == "No me gustan las películas de misterio"
    assert len(store.list_automatic_memory_log("alice")) == 2

    reopened = ConversationStore(path)
    assert len(reopened.get(cid, "alice")) == 2
    assert reopened.get(cid, "bob") is None
    assert reopened.list_memories("alice", "Cine")[0]["content"] == "No me gustan las películas de misterio"
    assert reopened.list_memories("alice", "Otro") == []
    assert reopened.list_memories("bob") == []
    assert reopened.get_summary(cid, "alice")["processed_count"] == 2

    captured = []

    class Available:
        def answer(self, messages, images=None):
            captured.extend(messages)
            return "Recibido."

    monkeypatch.setattr(module, "get_backend", lambda: Available())
    resumed = client.post("/api/chat", json={
        "conversation_id": cid, "project": "Cine", "text": "¿Qué películas prefiero?",
    })
    assert resumed.status_code == 200
    memory_context = captured[0]["content"]
    assert "No me gustan las películas de misterio" in memory_context
    assert "- Me gustan las películas de misterio" not in memory_context
    assert len(store.list_automatic_memory_log("alice")) == 2


def test_automatic_memory_index_failure_never_loses_committed_turn(monkeypatch, tmp_path):
    store, path, client = _setup(monkeypatch, tmp_path)

    def failed_index(*args, **kwargs):
        raise RuntimeError("index_unavailable")

    monkeypatch.setattr("iachat.auto_memory.learn", failed_index)

    class Available:
        def answer(self, messages, images=None):
            return "El mensaje quedó guardado."

    monkeypatch.setattr(module, "get_backend", lambda: Available())
    result = client.post("/api/chat", json={
        "text": "Prefiero respuestas breves.", "project": "IAchat",
    })
    assert result.status_code == 200
    cid = result.json()["conversation_id"]
    assert len(ConversationStore(path).get(cid, "alice")) == 2
    assert store.get_summary(cid, "alice")["processed_count"] == 2


def test_provider_failure_does_not_duplicate_preference_audit(monkeypatch, tmp_path):
    store, _, client = _setup(monkeypatch, tmp_path)

    class Unavailable:
        def answer(self, messages, images=None):
            raise RuntimeError("providers_unavailable")

    monkeypatch.setattr(module, "get_backend", lambda: Unavailable())
    first = client.post("/api/chat", json={
        "text": "Prefiero respuestas cortas.", "project": "IAchat",
    })
    assert first.status_code == 503
    cid = store.list_conversations("alice")[0]["id"]
    again = client.post("/api/chat", json={
        "conversation_id": cid, "project": "IAchat",
        "text": "prefiero   respuestas cortas!",
    })
    assert again.status_code == 503
    assert len(store.get(cid, "alice")) == 2
    assert len(store.list_memories("alice", "IAchat")) == 1
    assert len(store.list_automatic_memory_log("alice")) == 1
