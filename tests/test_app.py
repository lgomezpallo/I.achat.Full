from fastapi.testclient import TestClient
from iachat.app import app
from iachat.store import ConversationStore
import iachat.app as module

client = TestClient(app, base_url="https://testserver")

class FakeBackend:
    def answer(self, messages):
        return "respuesta " + str(len(messages))

def reset_store():
    module.store = ConversationStore(":memory:")

def test_health(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["component"] == "iachat"
    assert body["storage"] == "sqlite"

def test_home_is_chat_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert "IAchat" in response.text
    assert "/api/chat" in response.text

def test_chat_keeps_conversation(monkeypatch):
    reset_store()
    monkeypatch.setattr(module, "get_backend", lambda: FakeBackend())
    first = client.post("/api/chat", json={"text":"Hola"})
    assert first.status_code == 200
    session = first.json()["conversation_id"]
    second = client.post("/api/chat", json={"conversation_id":session,"text":"Seguimos"})
    assert second.status_code == 200
    assert len(second.json()["history"]) == 4
    restored = client.get("/api/conversations/" + session)
    assert restored.status_code == 200
    assert len(restored.json()["history"]) == 4

def test_delete_conversation(monkeypatch):
    reset_store()
    monkeypatch.setattr(module, "get_backend", lambda: FakeBackend())
    session = client.post("/api/chat", json={"text":"Hola"}).json()["conversation_id"]
    assert client.delete("/api/conversations/" + session).status_code == 200
    assert client.get("/api/conversations/" + session).status_code == 404

def test_unknown_session():
    reset_store()
    assert client.post("/api/chat", json={"conversation_id":"missing","text":"Hola"}).status_code == 404


def test_router_failure_does_not_create_fake_answer(monkeypatch):
    import httpx
    reset_store()

    class FailingBackend:
        def answer(self, messages):
            raise httpx.ConnectError("router offline")

    monkeypatch.setattr(module, "get_backend", lambda: FailingBackend())
    response = client.post("/api/chat", json={"text": "Hola"})
    assert response.status_code == 503
    assert response.json()["detail"] == "router_unavailable"
    assert module.store._db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0


def test_readiness_requires_router_credentials(monkeypatch):
    monkeypatch.delenv("ROUTER_URL", raising=False)
    monkeypatch.delenv("ROUTER_TOKEN", raising=False)
    assert client.get("/ready").status_code == 503
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    assert client.get("/ready").json()["mode"] == "router_only"

def test_router_backend_success_and_auth_failure(monkeypatch):
    from iachat.backend import RouterFirstBackend
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True, "text": "Respuesta de Router"}
    seen = []
    def reply(url, **kwargs):
        seen.append((url, kwargs["json"]["application_name"]))
        return Response()
    monkeypatch.setattr("iachat.backend.httpx.post", reply)
    assert RouterFirstBackend().answer([{"role": "user", "content": "Hola"}]) == "Respuesta de Router"
    assert seen == [("https://router.example/route", "iachat")]
    class Unauthorized:
        status_code = 401
    monkeypatch.setattr("iachat.backend.httpx.post", lambda *args, **kwargs: Unauthorized())
    import pytest
    with pytest.raises(RuntimeError, match="router_auth_rejected"):
        RouterFirstBackend().answer([{"role": "user", "content": "Hola"}])

def test_private_api_rejects_missing_session(monkeypatch):
    monkeypatch.setenv("IACHAT_PASSWORD", "test-pass")
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "test-secret")
    unauthenticated = client.get("/api/conversations/unknown")
    assert unauthenticated.status_code == 401
    authenticated = client.post("/auth/login", json={"password": "test-pass"})
    assert authenticated.status_code == 200
    assert client.get("/api/conversations/unknown").status_code == 404
    client.post("/auth/logout")
    monkeypatch.delenv("IACHAT_PASSWORD")
    monkeypatch.delenv("IACHAT_AUTH_SECRET")

def test_login_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("IACHAT_PASSWORD", "correct")
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "secret")
    assert client.post("/auth/login", json={"password": "wrong"}).status_code == 401

def test_installable_pwa():
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    info = manifest.json()
    assert info["display"] == "standalone"
    assert {i["sizes"] for i in info["icons"]} == {"192x192", "512x512"}
    assert 'rel="manifest"' in client.get("/").text
    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert "cache.addAll" in worker.text
    assert "/api/" in worker.text

def test_pwa_icons_are_png():
    for size in (192, 512):
        response = client.get(f"/icons/icon-{size}.png")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
        assert response.content.startswith(bytes.fromhex("89504e470d0a1a0a"))
        assert int.from_bytes(response.content[16:20], "big") == size
    assert client.get("/icons/icon-999.png").status_code == 404
