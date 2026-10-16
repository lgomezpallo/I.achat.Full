"""Verify opt-in Central persists state across HTTP requests."""
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.central_state import ConversationState
from iachat.central_storage import CentralStateStore
from iachat.store import ConversationStore


def test_central_http_recovers_state_and_clarifies_unknown_reference(monkeypatch, tmp_path):
    path = str(tmp_path / "shared.db")
    monkeypatch.setenv("IACHAT_DB", path)
    monkeypatch.setenv("IACHAT_CENTRAL_ENABLED", "1")
    module.store = ConversationStore(path)
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    client = TestClient(module.app)

    first = client.post("/api/chat", json={"text": "Hola"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]

    db = CentralStateStore(path)
    assert db.load("smoke", conversation_id) is not None
    db.save("smoke", conversation_id, ConversationState(active_topic="Obra 1058"))
    db.close()

    # The persisted topic is available, so this is delegated rather than
    # incorrectly clarified. A model is deliberately not called in this test.
    class Backend:
        def answer(self, messages, images=None):
            return "Respuesta de prueba"
    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    followup = client.post("/api/chat", json={
        "conversation_id": conversation_id, "text": "¿Qué pasó ahí?"
    })
    assert followup.status_code == 200
    assert followup.json()["answer"] == "Respuesta de prueba"

    unknown = client.post("/api/chat", json={"text": "¿Qué pasó ahí?"})
    assert unknown.status_code == 200
    assert unknown.json()["answer"] == "¿A qué tema te referís?"
