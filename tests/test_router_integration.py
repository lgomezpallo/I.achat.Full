import pytest
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.app import app
from iachat.backend import RouterBackend
from iachat.store import ConversationStore


@pytest.fixture(autouse=True)
def authenticated_client(monkeypatch):
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")

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
    assert outgoing[1]["conversation"] == [
        {"role": "user", "content": "Mi color favorito es azul"},
        {"role": "assistant", "content": "Primera respuesta"},
    ]
    assert "decompose" not in outgoing[1]
    assert len(ConversationStore(str(dbfile)).get(cid)) == 4


def test_long_short_turn_history_respects_actual_router_request_contract(monkeypatch, tmp_path):
    """Many short turns must never trigger Router's 100-message validation error."""
    module.store = ConversationStore(str(tmp_path / "long-chat.db"))
    monkeypatch.setattr(module, "get_backend", lambda: RouterBackend("http://router:8010", token="testing"))
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Mensaje {i}"}
        for i in range(240)
    ]
    module.store.put("many-turns", history, "admin", "")
    captured = []

    def fake_router(url, **kwargs):
        payload = kwargs["json"]
        captured.append(payload)
        assert url == "http://router:8010/route"
        assert len(payload["conversation"]) <= 100
        assert payload["conversation"][0]["role"] == "user"
        assert payload["conversation"][-1] == history[-1]
        assert payload["task"] == "¿Qué recordás?"
        return RealFormatRouterResponse("No tengo todos los mensajes anteriores.")

    monkeypatch.setattr("iachat.backend.httpx.post", fake_router)
    result = TestClient(app).post(
        "/api/chat", json={"conversation_id": "many-turns", "text": "¿Qué recordás?"}
    )
    assert result.status_code == 200
    assert len(captured) == 1
    assert len(module.store.get("many-turns", "admin")) == 242
    assert "mensajes anteriores" in captured[0]["context"]


def test_router_auth_failure_does_not_corrupt_stored_chat(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "router-failure.db"))
    module.store.put("existing", [
        {"role": "user", "content": "Mi bicicleta es verde."},
        {"role": "assistant", "content": "Entendido."},
    ], "admin", "")
    monkeypatch.setattr(module, "get_backend", lambda: RouterBackend("http://router:8010", token="testing"))

    class Unauthorized:
        status_code = 401

    def reject_request(url, **kwargs):
        assert url == "http://router:8010/route"
        return Unauthorized()

    monkeypatch.setattr("iachat.backend.httpx.post", reject_request)
    before = module.store.get("existing", "admin")
    response = TestClient(app).post(
        "/api/chat", json={"conversation_id": "existing", "text": "¿De qué color es?"}
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "router_auth_rejected"
    assert module.store.get("existing", "admin") == before


def test_router_invalid_success_payload_does_not_persist_fake_answer(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "router-invalid.db"))
    history = [
        {"role": "user", "content": "El perro se llama Tango."},
        {"role": "assistant", "content": "Entendido."},
    ]
    module.store.put("existing", history, "admin", "")
    monkeypatch.setattr(module, "get_backend", lambda: RouterBackend("http://router:8010", token="testing"))

    class InvalidResponse:
        status_code = 200
        def json(self):
            return {"ok": True, "text": "", "provider": "test", "model": "test"}

    monkeypatch.setattr("iachat.backend.httpx.post", lambda url, **kwargs: InvalidResponse())
    result = TestClient(app).post("/api/chat", json={
        "conversation_id": "existing", "text": "¿Cómo se llama el perro?"
    })
    assert result.status_code == 503
    assert result.json()["detail"] == "router_failed"
    assert module.store.get("existing", "admin") == history
