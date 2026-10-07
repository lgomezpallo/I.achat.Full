from fastapi.testclient import TestClient
from iachat.app import app, sessions
import iachat.app as module

client = TestClient(app)

class FakeBackend:
    def answer(self, messages):
        return "respuesta " + str(len(messages))

def test_health():
    assert client.get("/health").json()["status"] == "ok"

def test_chat_keeps_conversation(monkeypatch):
    sessions.clear()
    monkeypatch.setattr(module, "get_backend", lambda: FakeBackend())
    first = client.post("/api/chat", json={"text":"Hola"})
    assert first.status_code == 200
    session = first.json()["conversation_id"]
    second = client.post("/api/chat", json={"conversation_id":session,"text":"Seguimos"})
    assert second.status_code == 200
    assert len(second.json()["history"]) == 4

def test_unknown_session():
    assert client.post("/api/chat", json={"conversation_id":"missing","text":"Hola"}).status_code == 404
