from fastapi.testclient import TestClient
import iachat.app as module
from iachat.app import app
from iachat.backend import RouterBackend
from iachat.store import ConversationStore


class RealFormatRouterResponse:
    status_code = 200
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "ok": True,
            "text": self.text,
            "provider": "provider-from-test",
            "model": "model-from-test",
            "attempts": [],
            "decisions": [],
            "error": None,
        }


def test_two_turns_through_router_contract_and_persistence(monkeypatch, tmp_path):
    dbfile = tmp_path / "chat.db"
    module.store = ConversationStore(str(dbfile))
    monkeypatch.setattr(module, "get_backend", lambda: RouterBackend("http://router:8010", token="testing"))
    outgoing = []

    def fake_post(url, **kwargs):
        assert url == "http://router:8010/route"
        assert kwargs["headers"] == {"Authorization": "Bearer testing"}
        outgoing.append(kwargs["json"])
        return RealFormatRouterResponse("Primera respuesta" if len(outgoing) == 1 else "Segunda respuesta")

    monkeypatch.setattr("iachat.backend.httpx.post", fake_post)
    client = TestClient(app)

    first = client.post("/api/chat", json={"text": "Mi color favorito es azul"})
    assert first.status_code == 200
    cid = first.json()["conversation_id"]
    second = client.post("/api/chat", json={"conversation_id": cid, "text": "¿Qué color dije?"})
    assert second.status_code == 200
    assert outgoing[0]["task"] == "Mi color favorito es azul"
    assert outgoing[1]["task"] == "¿Qué color dije?"
    assert outgoing[1]["context"] == (
        "user: Mi color favorito es azul\nassistant: Primera respuesta"
    )
    assert outgoing[1]["decompose"] is False
    assert len(ConversationStore(str(dbfile)).get(cid)) == 4
