from fastapi.testclient import TestClient
import iachat.app as module
from iachat.central_storage import CentralStateStore
from iachat.central_state import explicit_topic
from iachat.store import ConversationStore


def test_explicit_topic_is_conservative():
    assert explicit_topic("Seguimos con la obra 1058") == "Obra 1058"
    assert explicit_topic("Presupuesto N° 1168") == "Obra 1168"
    assert explicit_topic("El 16 de octubre") is None
    assert explicit_topic("¿Qué pasó ahí?") is None


def test_explicit_topic_survives_next_http_request(monkeypatch, tmp_path):
    path = str(tmp_path / "shared.db")
    monkeypatch.setenv("IACHAT_DB", path)
    monkeypatch.setenv("IACHAT_CENTRAL_ENABLED", "1")
    module.store = ConversationStore(path)
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")

    class Backend:
        calls = []
        def answer(self, messages, images=None):
            self.calls.append(messages)
            return "Respuesta simulada"
    backend = Backend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)
    client = TestClient(module.app)
    first = client.post("/api/chat", json={"text": "Contame sobre la obra 1058"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    db = CentralStateStore(path)
    assert db.load("smoke", conversation_id).active_topic == "Obra 1058"
    db.close()

    second = client.post("/api/chat", json={
        "conversation_id": conversation_id, "text": "¿Qué pasó ahí?"
    })
    assert second.status_code == 200
    assert any("Obra 1058" in m["content"] for m in backend.calls[-1] if m["role"] == "system")
