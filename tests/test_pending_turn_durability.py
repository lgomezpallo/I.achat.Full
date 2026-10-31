"""Regression for durable user turns and atomic image persistence.

These are isolated HTTP tests with a fake provider, NOT production E2E.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import iachat.app as module
from iachat.store import ConversationStore


PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=="


def _setup(monkeypatch, tmp_path):
    path = str(tmp_path / "pending.db")
    store = ConversationStore(path)
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args: SimpleNamespace(action="skip"),
    )
    return store, path, TestClient(module.app)


def test_failed_provider_retains_pending_turn_and_image_after_reopen(monkeypatch, tmp_path):
    store, path, client = _setup(monkeypatch, tmp_path)

    class Unavailable:
        def answer(self, messages, images=None):
            raise RuntimeError("providers_unavailable")

    monkeypatch.setattr(module, "get_backend", lambda: Unavailable())
    response = client.post("/api/chat", json={
        "text": "Decidimos guardar esta imagen para el proyecto Atlas.",
        "project": "Atlas",
        "attachments": [{"name": "evidencia.png", "content_base64": PNG}],
    })
    assert response.status_code == 503
    conversations = store.list_conversations("alice")
    assert len(conversations) == 1
    conversation_id = conversations[0]["id"]

    reopened = ConversationStore(path)
    history = reopened.get(conversation_id, "alice")
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert "evidencia.png" in history[0]["content"]
    assert PNG not in repr(history)
    assert reopened.get_summary(conversation_id, "alice")["processed_count"] == 1
    images = reopened.images_for_conversation(conversation_id, "alice")
    assert len(images) == 1
    assert images[0]["message_index"] == 0
    assert images[0]["data_url"] == "data:image/png;base64," + PNG
    assert reopened.get(conversation_id, "bob") is None
    assert reopened.images_for_conversation(conversation_id, "bob") == []


def test_followup_after_provider_failure_keeps_both_user_turns(monkeypatch, tmp_path):
    store, path, client = _setup(monkeypatch, tmp_path)
    store.put("c", [
        {"role": "user", "content": "Decidimos usar PostgreSQL para Atlas."},
        {"role": "assistant", "content": "Anotado."},
    ], "alice", "Atlas")

    class Unavailable:
        def answer(self, messages, images=None):
            raise RuntimeError("providers_unavailable")

    monkeypatch.setattr(module, "get_backend", lambda: Unavailable())
    failed = client.post("/api/chat", json={
        "conversation_id": "c", "project": "Atlas",
        "text": "Falta revisar el respaldo del proyecto Atlas.",
    })
    assert failed.status_code == 503

    captured = []

    class Available:
        def answer(self, messages, images=None):
            captured.extend(messages)
            return "Recibido."

    monkeypatch.setattr(module, "get_backend", lambda: Available())
    resumed = client.post("/api/chat", json={
        "conversation_id": "c", "project": "Atlas",
        "text": "¿Qué habíamos decidido?",
    })
    assert resumed.status_code == 200, resumed.text
    saved = ConversationStore(path).get("c", "alice")
    assert [m["role"] for m in saved] == ["user", "assistant", "user", "user", "assistant"]
    assert "Falta revisar el respaldo" in saved[2]["content"]
    assert "Decidimos usar PostgreSQL" in repr(captured)


def test_current_image_is_not_reselected_as_previous(monkeypatch, tmp_path):
    store, _, client = _setup(monkeypatch, tmp_path)
    calls = []

    class Available:
        def answer(self, messages, images=None):
            calls.append((messages, images))
            return "Imagen recibida."

    monkeypatch.setattr(module, "get_backend", lambda: Available())
    first = client.post("/api/chat", json={
        "text": "Describí esta imagen.",
        "attachments": [{"name": "primera.png", "content_base64": PNG}],
    })
    assert first.status_code == 200, first.text
    cid = first.json()["conversation_id"]
    second = client.post("/api/chat", json={
        "conversation_id": cid,
        "text": "Compará con la anterior.",
        "attachments": [{"name": "segunda.png", "content_base64": PNG}],
    })
    assert second.status_code == 200, second.text
    assert len(calls) == 2
    assert len(calls[0][1]) == 1
    assert len(calls[1][1]) == 2
    assert "Imagen 1: primera.png" in calls[1][0][-1]["content"]
    assert "Imagen 2: segunda.png" in calls[1][0][-1]["content"]
    assert [i["message_index"] for i in store.images_for_conversation(cid, "alice")] == [0, 2]


def test_invalid_image_append_rolls_back_text_and_summary(tmp_path):
    store = ConversationStore(str(tmp_path / "rollback.db"))
    with pytest.raises(ValueError, match="image_attachments_require_user_turn"):
        store.put(
            "c", [{"role": "assistant", "content": "No user turn"}],
            "alice", image_attachments=[("x.png", "data:image/png;base64,AA==")],
        )
    assert store.get("c", "alice") is None
    assert store.get_summary("c", "alice") is None
    assert store.images_for_conversation("c", "alice") == []
