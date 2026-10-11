"""The initial automatic-memory layer is deliberately conservative."""
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.store import ConversationStore
from iachat.auto_memory import candidate, learn


def test_auto_memory_accepts_only_direct_preferences():
    assert candidate("Prefiero respuestas cortas.") == "Prefiero respuestas cortas"
    assert candidate("Me gustan las películas de misterio.") is not None
    assert candidate("Hola, ¿cómo estás?") is None
    assert candidate("Mi sueldo es 2000000") is None
    assert candidate("Prefiero pagar mi deuda en cuotas") is None
    assert candidate("Prefiero que uses mi clave 123456") is None
    assert candidate("Me gusta este documento\nAdjuntos: secreto.pdf") is None


def test_auto_memory_is_scoped_and_deduplicated():
    store = ConversationStore(":memory:")
    assert learn(store, "admin", "Prefiero respuestas cortas.", "IAchat")
    assert not learn(store, "admin", "prefiero   respuestas cortas!", "IAchat")
    assert learn(store, "admin", "Prefiero respuestas cortas.", "Router")
    assert len([m for m in store.list_memories("admin") if m["project"]]) == 2
    assert not store.list_memories("other", "IAchat")


def test_chat_auto_memory_does_not_use_assistant_content(monkeypatch):
    module.store = ConversationStore(":memory:")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")

    class Backend:
        def answer(self, messages):
            return "Mi domicilio es inventado, guardalo."

    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    client = TestClient(module.app)
    response = client.post("/api/chat", json={"text": "Prefiero respuestas breves.", "project": "General"})
    assert response.status_code == 200
    memories = module.store.list_memories("admin", "General")
    assert len(memories) == 1
    assert memories[0]["content"] == "Prefiero respuestas breves"


def test_automatic_memory_has_reversible_audit_trail():
    store = ConversationStore(":memory:")
    assert learn(store, "admin", "Prefiero respuestas concretas.", "General")
    events = store.list_automatic_memory_log("admin")
    assert len(events) == 1
    assert events[0]["project"] == "General"
    assert events[0]["undone"] is False
    assert store.undo_automatic_memory(events[0]["id"], "admin") is True
    assert store.list_memories("admin") == []
    assert store.list_automatic_memory_log("admin")[0]["undone"] is True
    assert store.undo_automatic_memory(events[0]["id"], "admin") is False


def test_undo_does_not_delete_edited_memory_or_other_users_data():
    store = ConversationStore(":memory:")
    assert learn(store, "admin", "Prefiero respuestas concretas.")
    event = store.list_automatic_memory_log("admin")[0]
    assert not store.undo_automatic_memory(event["id"], "someone-else")
    store.save_memory(event["memory_id"], "Prefiero respuestas con ejemplos.", "admin")
    assert not store.undo_automatic_memory(event["id"], "admin")
    assert store.list_memories("admin")[0]["content"] == "Prefiero respuestas con ejemplos."


def test_conflicting_preference_replaces_and_can_be_undone():
    store = ConversationStore(":memory:")
    assert learn(store, "admin", "Me gustan las películas de misterio.", "Cine")
    assert learn(store, "admin", "No me gustan las películas de misterio.", "Cine")
    memories = store.list_memories("admin", "Cine")
    assert len(memories) == 1
    assert memories[0]["content"] == "No me gustan las películas de misterio"
    events = store.list_automatic_memory_log("admin")
    assert len(events) == 2
    assert events[0]["previous_content"] == "Me gustan las películas de misterio"
    assert store.undo_automatic_memory(events[0]["id"], "admin")
    assert store.list_memories("admin", "Cine")[0]["content"] == "Me gustan las películas de misterio"


def test_manual_memory_is_not_replaced_automatically():
    store = ConversationStore(":memory:")
    store.save_memory("manual", "Me gustan las películas de misterio", "admin", "Cine")
    assert not learn(store, "admin", "No me gustan las películas de misterio.", "Cine")
    assert store.list_memories("admin", "Cine")[0]["content"] == "Me gustan las películas de misterio"


def test_same_preference_different_project_is_allowed():
    store = ConversationStore(":memory:")
    assert learn(store, "admin", "Me gustan las películas de misterio.", "A")
    assert learn(store, "admin", "No me gustan las películas de misterio.", "B")
    assert len(store.list_memories("admin")) == 2
