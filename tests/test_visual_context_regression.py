"""Regression coverage for multi-turn image references through the real HTTP chat API.

The Router transport is replaced at the network boundary, not the IAchat backend.
This verifies which original image bytes and conversation turns IAchat actually sends.
"""
import base64

from fastapi.testclient import TestClient

import iachat.app as module
from iachat.store import ConversationStore


PNG = base64.b64encode(bytes.fromhex("89504e470d0a1a0a") + b"visual-regression").decode()


def test_followup_sends_original_image_to_router(monkeypatch):
    module.store = ConversationStore(":memory:")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    requests = []

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "Respuesta de prueba"}

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    with TestClient(module.app, base_url="https://testserver") as client:
        first = client.post("/api/chat", json={
            "text": "¿Qué aparece en esta imagen?",
            "attachments": [{"name": "foto.png", "content_base64": PNG}],
        })
        assert first.status_code == 200, first.text
        cid = first.json()["conversation_id"]
        followup = client.post("/api/chat", json={
            "conversation_id": cid,
            "text": "¿Qué se ve en la foto anterior?",
        })
        assert followup.status_code == 200, followup.text

    assert len(requests) == 2
    assert requests[0]["required_capabilities"] == ["chat", "vision"]
    assert requests[1]["required_capabilities"] == ["chat", "vision"]
    assert requests[1]["images"] == requests[0]["images"]
    assert "foto.png" in requests[1]["task"]
    assert any(item["role"] == "assistant" for item in requests[1]["conversation"])


def test_two_image_comparison_sends_both_originals(monkeypatch):
    module.store = ConversationStore(":memory:")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    requests = []

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "Respuesta de prueba"}

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    with TestClient(module.app, base_url="https://testserver") as client:
        a = client.post("/api/chat", json={
            "text": "Esta es la primera foto",
            "attachments": [{"name": "primera.png", "content_base64": PNG}],
        })
        assert a.status_code == 200, a.text
        cid = a.json()["conversation_id"]
        b = client.post("/api/chat", json={
            "conversation_id": cid,
            "text": "Esta es la segunda foto",
            "attachments": [{"name": "segunda.png", "content_base64": PNG}],
        })
        assert b.status_code == 200, b.text
        c = client.post("/api/chat", json={
            "conversation_id": cid,
            "text": "Compará las dos imágenes anteriores",
        })
        assert c.status_code == 200, c.text

    assert len(requests) == 3
    assert requests[2]["required_capabilities"] == ["chat", "vision"]
    assert len(requests[2]["images"]) == 2
    assert "primera.png" in requests[2]["task"]
    assert "segunda.png" in requests[2]["task"]


def test_new_image_compared_to_previous_is_not_discarded(monkeypatch):
    module.store = ConversationStore(":memory:")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    requests = []

    class Response:
        status_code = 200

        def json(self):
            return {"ok": True, "text": "Respuesta de prueba"}

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return Response()

    monkeypatch.setattr("iachat.backend.httpx.post", post)
    with TestClient(module.app, base_url="https://testserver") as client:
        first = client.post("/api/chat", json={
            "text": "Mirá esta foto",
            "attachments": [{"name": "antes.png", "content_base64": PNG}],
        })
        assert first.status_code == 200, first.text
        second = client.post("/api/chat", json={
            "conversation_id": first.json()["conversation_id"],
            "text": "¿Qué cambió respecto de la anterior?",
            "attachments": [{"name": "despues.png", "content_base64": PNG}],
        })
        assert second.status_code == 200, second.text

    assert len(requests) == 2
    assert len(requests[1]["images"]) == 2
    assert "antes.png" in requests[1]["task"]
    assert "despues.png" in requests[1]["task"]
