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
