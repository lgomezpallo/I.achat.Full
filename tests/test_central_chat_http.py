"""HTTP contract: opt-in Central replies locally and delegates open requests."""
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.store import ConversationStore


class CaptureBackend:
    def __init__(self):
        self.calls = 0

    def answer(self, messages, images=None):
        self.calls += 1
        return "Respuesta desde Router simulado"


def test_central_opt_in_and_router_fallback(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "chat.db"))
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    monkeypatch.setenv("IACHAT_CENTRAL_ENABLED", "1")
    backend = CaptureBackend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)
    client = TestClient(module.app)

    greeting = client.post("/api/chat", json={"text": "Hola"})
    assert greeting.status_code == 200
    assert greeting.json()["answer"] == "¡Hola! ¿En qué te puedo ayudar?"
    assert backend.calls == 0
    conversation_id = greeting.json()["conversation_id"]

    open_request = client.post("/api/chat", json={
        "conversation_id": conversation_id, "text": "Explicá la fotosíntesis."
    })
    assert open_request.status_code == 200
    assert open_request.json()["answer"] == "Respuesta desde Router simulado"
    assert backend.calls == 1
    assert len(open_request.json()["history"]) == 4


def test_central_disabled_keeps_existing_router_path(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "chat.db"))
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    monkeypatch.delenv("IACHAT_CENTRAL_ENABLED", raising=False)
    backend = CaptureBackend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)
    response = TestClient(module.app).post("/api/chat", json={"text": "Hola"})
    assert response.status_code == 200
    assert backend.calls == 1
