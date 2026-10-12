"""End-to-end image attachment contract without production data or external inference."""
import base64
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.attachments import AttachmentError, extract_images
from iachat.store import ConversationStore
import pytest

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg=="


class CaptureBackend:
    def __init__(self):
        self.messages = None
        self.images = None

    def answer(self, messages, images=None):
        self.messages = messages
        self.images = images
        return "Es una imagen de prueba."


def test_image_to_backend_is_ephemeral(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "images.db"))
    module.store.create_user("smoke", "test-only-secret")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "smoke")
    backend = CaptureBackend()
    monkeypatch.setattr(module, "get_backend", lambda: backend)

    client = TestClient(module.app)
    response = client.post("/api/chat", json={
        "text": "Describí esta imagen.",
        "attachments": [{"name": "foto.png", "content_base64": PNG}]
    })
    assert response.status_code == 200, response.text
    conversation = response.json()
    assert backend.images == ["data:image/png;base64," + PNG]
    assert backend.messages[-1]["content"] == "Describí esta imagen."
    assert "foto.png" in conversation["history"][-2]["content"]
    assert PNG not in repr(conversation["history"])
    assert PNG not in repr(module.store.get(conversation["conversation_id"], "smoke"))


def test_image_magic_and_size_validation():
    from types import SimpleNamespace
    valid = SimpleNamespace(name="foto.png", content_base64=PNG)
    assert extract_images([valid])[1] == ["foto.png"]
    with pytest.raises(AttachmentError):
        extract_images([SimpleNamespace(name="falsa.png", content_base64=base64.b64encode(b"no-png").decode())])
    with pytest.raises(AttachmentError):
        extract_images([SimpleNamespace(name="foto.svg", content_base64=PNG)])
