from fastapi.testclient import TestClient
from iachat.app import app
from iachat.store import ConversationStore
import iachat.app as module

client = TestClient(app, base_url="https://testserver")

# Legacy functional tests run as an authenticated account. Dedicated security tests
# exercise real cookie verification and must not receive this bypass.
import pytest

@pytest.fixture(autouse=True)
def authenticated_functional_test(request, monkeypatch):
    if request.node.name not in {
        "test_private_api_rejects_missing_session",
        "test_login_rejects_wrong_password",
    }:
        monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")


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


def test_server_history_survives_new_store_instance_and_deletes(monkeypatch, tmp_path):
    db = str(tmp_path / "shared.db")
    module.store = ConversationStore(db)
    monkeypatch.setattr(module, "get_backend", lambda: FakeBackend())
    first = client.post("/api/chat", json={"text": "Tema persistente"}).json()
    cid = first["conversation_id"]
    module.store = ConversationStore(db)
    listing = client.get("/api/conversations")
    assert listing.status_code == 200
    assert listing.json()["conversations"][0]["id"] == cid
    assert listing.json()["conversations"][0]["title"] == "Tema persistente"
    assert client.get(f"/api/conversations/{cid}").status_code == 200
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    assert client.get("/api/conversations").json()["conversations"] == []


def test_memories_survive_restart_and_are_sent_as_context(monkeypatch, tmp_path):
    db = str(tmp_path / "memory.db")
    module.store = ConversationStore(db)
    created = client.post("/api/memories", json={"content": "Prefiero respuestas en español"})
    assert created.status_code == 201
    mid = created.json()["id"]
    module.store = ConversationStore(db)
    assert client.get("/api/memories").json()["memories"][0]["id"] == mid
    captured = []
    class CaptureBackend:
        def answer(self, messages):
            captured.extend(messages)
            return "OK"
    monkeypatch.setattr(module, "get_backend", lambda: CaptureBackend())
    response = client.post("/api/chat", json={"text": "Hola"})
    assert response.status_code == 200
    assert captured[0]["role"] == "system"
    assert "Prefiero respuestas en español" in captured[0]["content"]
    assert captured[-1] == {"role": "user", "content": "Hola"}
    assert client.put(f"/api/memories/{mid}", json={"content":"Prefiero mensajes breves"}).status_code == 200
    assert client.get("/api/memories").json()["memories"][0]["content"] == "Prefiero mensajes breves"
    assert client.delete(f"/api/memories/{mid}").status_code == 200
    assert client.get("/api/memories").json()["memories"] == []
    assert client.delete(f"/api/memories/{mid}").status_code == 404


def test_memory_suggestions_require_review_and_do_not_auto_save(monkeypatch):
    module.store = ConversationStore(":memory:")
    class ConversationBackend:
        def answer(self, messages):
            if "hasta 3 recuerdos" in messages[-1]["content"]:
                return '["Prefiere respuestas breves", "Usa IAchat en el teléfono"]'
            return "Respuesta"
    monkeypatch.setattr(module, "get_backend", lambda: ConversationBackend())
    cid = client.post("/api/chat", json={"text":"Prefiero respuestas breves"}).json()["conversation_id"]
    result = client.post("/api/memories/suggest", json={"conversation_id":cid})
    assert result.status_code == 200
    assert result.json()["suggestions"] == ["Prefiere respuestas breves", "Usa IAchat en el teléfono"]
    assert client.get("/api/memories").json()["memories"] == []
    assert client.post("/api/memories",json={"content":result.json()["suggestions"][0]}).status_code == 201
    second = client.post("/api/memories/suggest", json={"conversation_id":cid})
    assert second.json()["suggestions"] == ["Usa IAchat en el teléfono"]

def test_memory_suggestions_reject_invalid_router_output(monkeypatch):
    module.store = ConversationStore(":memory:")
    class InvalidBackend:
        def answer(self, messages):
            if "máximo de 3 recuerdos" in messages[-1]["content"]:
                return "I cannot produce JSON"
            return "OK"
    monkeypatch.setattr(module, "get_backend", lambda: InvalidBackend())
    cid = client.post("/api/chat", json={"text":"Hola"}).json()["conversation_id"]
    assert client.post("/api/memories/suggest", json={"conversation_id":cid}).status_code == 502
    assert client.post("/api/memories/suggest", json={"conversation_id":"missing"}).status_code == 404


def test_router_status_does_not_confuse_health_with_routing(monkeypatch):
    monkeypatch.delenv("ROUTER_URL", raising=False)
    monkeypatch.delenv("ROUTER_TOKEN", raising=False)
    missing = client.get("/api/router/status")
    assert missing.status_code == 200
    assert missing.json()["configured"] is False
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "secret")
    class Healthy:
        status_code = 200
        def json(self):
            return {"status": "ok", "providers": []}
    monkeypatch.setattr("iachat.app.httpx.get", lambda *args, **kwargs: Healthy())
    result = client.get("/api/router/status").json()
    assert result["reachable"] is True
    assert result["routing_verified"] is False
    class Failed:
        status_code = 503
    monkeypatch.setattr("iachat.app.httpx.get", lambda *args, **kwargs: Failed())
    assert client.get("/api/router/status").json()["reachable"] is False


def test_router_preserves_user_language_instruction(monkeypatch):
    from iachat.backend import RouterFirstBackend
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "test-token")
    captured = {}
    class Response:
        status_code = 200
        def json(self):
            return {"ok": True, "text": "Hola, ¿cómo estás?"}
    def post(url, **kwargs):
        captured.update(kwargs["json"])
        return Response()
    monkeypatch.setattr("iachat.backend.httpx.post", post)
    answer = RouterFirstBackend().answer([
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Buen día"},
        {"role": "user", "content": "¿Cómo estás?"},
    ])
    assert answer == "Hola, ¿cómo estás?"
    assert captured["task"] == "¿Cómo estás?"
    assert "mismo idioma" in captured["context"]
    assert captured["conversation"][0] == {"role": "user", "content": "Hola"}
    assert "decompose" not in captured  # Router uses its automatic default
