from fastapi.testclient import TestClient
from iachat.app import app
from iachat.store import ConversationStore
import iachat.app as module

client = TestClient(app)

class FakeBackend:
    def answer(self, messages):
        return "respuesta " + str(len(messages))

def reset_store():
    module.store = ConversationStore(":memory:")

def test_health(monkeypatch):
    monkeypatch.delenv("ROUTER_URL", raising=False)
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["router_configured"] is False
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


def test_readiness_requires_router_connection(monkeypatch):
    import httpx
    monkeypatch.delenv("ROUTER_URL", raising=False)
    assert client.get("/ready").status_code == 503
    monkeypatch.setenv("ROUTER_URL", "http://router:8010")

    class HealthyResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(module.httpx, "get", lambda *args, **kwargs: HealthyResponse())
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["router"] == "reachable"

    def no_router(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(module.httpx, "get", no_router)
    assert client.get("/ready").status_code == 503
