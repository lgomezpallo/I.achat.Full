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
