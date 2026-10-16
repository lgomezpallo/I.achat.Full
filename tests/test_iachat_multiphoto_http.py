"""HTTP integration checks for IAchat's everyday multi-image flow."""
import base64
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.store import ConversationStore

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=="


class Backend:
    def __init__(self):
        self.calls = []

    def answer(self, messages, images=None):
        self.calls.append((messages, images))
        return "Respuesta de prueba"


def test_two_images_and_followup_reuse_originals(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "chat.db"))
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    backend = Backend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)
    client = TestClient(module.app)
    first = client.post("/api/chat", json={
        "text": "Compará estas dos imágenes",
        "attachments": [
            {"name": "primera.png", "content_base64": PNG},
            {"name": "segunda.png", "content_base64": PNG},
        ],
    })
    assert first.status_code == 200, first.text
    assert len(backend.calls[0][1]) == 2
    assert "Imagen 1: primera.png" in backend.calls[0][0][-1]["content"]
    assert "Imagen 2: segunda.png" in backend.calls[0][0][-1]["content"]
    conversation_id = first.json()["conversation_id"]
    followup = client.post("/api/chat", json={
        "conversation_id": conversation_id, "text": "Compará las dos fotos anteriores"
    })
    assert followup.status_code == 200, followup.text
    assert len(backend.calls[1][1]) == 2
    assert len(followup.json()["history"]) == 4
    assert PNG not in repr(followup.json()["history"])


def test_five_images_are_accepted(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "five.db"))
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    backend = Backend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)
    response = TestClient(module.app).post("/api/chat", json={
        "text": "Compará las cinco fotos",
        "attachments": [
            {"name": f"foto-{i}.png", "content_base64": PNG}
            for i in range(1, 6)
        ],
    })
    assert response.status_code == 200, response.text
    assert len(backend.calls[0][1]) == 5
    assert "Imagen 5: foto-5.png" in backend.calls[0][0][-1]["content"]
