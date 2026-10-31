"""Offline regressions for the same IAchat engine in a separate work instance.

These tests never connect to Oracle, Router, PostgreSQL or a provider account.
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import iachat.app as app_module
from iachat.store import ConversationStore
from iachat.file_workspace import FileWorkspace
from iachat.structured_data import StructuredStore


class FakeConversationalBackend:
    def __init__(self):
        self.messages = []

    def answer(self, messages, images=None):
        self.messages.append(messages)
        return "No guardé ninguna novedad oficial. Falta confirmación en PostgreSQL."


def test_go_profile_reuses_chat_without_automatic_sqlite_work_writes(monkeypatch, tmp_path):
    path = str(tmp_path / "work-instance.db")
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setattr(app_module, "store", ConversationStore(path))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(path))
    monkeypatch.setattr(app_module, "structured_store", StructuredStore(path))
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")
    assert app_module.store.create_user("worker", "test-only-password")
    # A stored memory must never replace the trusted work-only safety policy.
    app_module.store.save_memory("test-memory", "Turno de mañana", "worker")
    backend = FakeConversationalBackend()
    monkeypatch.setattr(app_module, "get_backend", lambda: backend)
    monkeypatch.setattr(
        app_module, "handle_structured_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("work profile must not write via SQLite structured collections")
        ),
    )
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="none"),
    )
    monkeypatch.setattr("iachat.tool_planner.is_file_action_candidate", lambda _: False)
    monkeypatch.setattr("iachat.auto_memory.learn", lambda *args: None)

    with TestClient(app_module.app, base_url="https://go.test") as first:
        result = first.post("/api/chat", json={
            "text": "Registrá 8 horas ejecutadas para la obra 1190"
        })
        assert result.status_code == 200, result.text
        conversation_id = result.json()["conversation_id"]
        assert "No guardé ninguna novedad oficial" in result.json()["answer"]
        assert app_module.structured_store.collections("worker") == []
        assert any("Turno de mañana" in m["content"] for m in backend.messages[-1] if m["role"] == "system")
        assert any(
            "NO modifica registros oficiales" in m["content"]
            for m in backend.messages[-1] if m["role"] == "system"
        )
    # A second browser session reads the same isolated work-instance SQLite.
    with TestClient(app_module.app, base_url="https://go.test") as second:
        history = second.get("/api/conversations/" + conversation_id)
        assert history.status_code == 200
        assert len(history.json()["history"]) == 2


def test_personal_profile_keeps_existing_structured_data_route(monkeypatch, tmp_path):
    path = str(tmp_path / "personal-instance.db")
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.setattr(app_module, "store", ConversationStore(path))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(path))
    monkeypatch.setattr(app_module, "structured_store", StructuredStore(path))
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "personal")
    assert app_module.store.create_user("personal", "test-only-password")
    calls = []
    def existing_handler(*args):
        calls.append(args)
        return {"answer": "Ruta personal conservada."}
    monkeypatch.setattr(app_module, "handle_structured_chat", existing_handler)
    with TestClient(app_module.app, base_url="https://personal.test") as client:
        response = client.post("/api/chat", json={"text": "anotá un gasto"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Ruta personal conservada."
    assert len(calls) == 1


def test_two_sqlite_instances_do_not_share_users_memories_or_conversations(tmp_path):
    personal_path = tmp_path / "personal.db"
    work_path = tmp_path / "work.db"
    personal = ConversationStore(str(personal_path))
    work = ConversationStore(str(work_path))
    assert personal.create_user("alice", "test-only-password")
    assert work.create_user("alice", "another-test-password")
    personal.put("private-conversation", [{"role": "user", "content": "personal"}], "alice")
    personal.save_memory("memory-1", "private memory", "alice")
    assert work.get("private-conversation", "alice") is None
    assert work.list_memories("alice") == []
    assert work.verify_user("alice", "another-test-password")
    assert not work.verify_user("alice", "test-only-password")
