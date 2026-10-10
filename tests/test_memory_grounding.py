"""Regression tests: memory suggestions must not learn assistant claims."""
from fastapi.testclient import TestClient
import iachat.app as module
from iachat.store import ConversationStore


def test_suggestions_only_quote_user_messages(monkeypatch):
    module.store = ConversationStore(":memory:")
    module.store.put("example", [
        {"role": "user", "content": "Prefiero respuestas cortas."},
        {"role": "assistant", "content": "Tu domicilio es Calle Inventada 123."},
        {"role": "user", "content": "Revisá el PDF.\n\nAdjuntos: resumen.pdf"},
    ])
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")
    captured = []

    class CaptureBackend:
        def answer(self, messages):
            captured.append(messages[-1]["content"])
            return '["Prefiere respuestas cortas"]'

    monkeypatch.setattr(module, "get_backend", lambda: CaptureBackend())
    response = TestClient(module.app).post(
        "/api/memories/suggest", json={"conversation_id": "example"}
    )
    assert response.status_code == 200
    assert response.json()["suggestions"] == ["Prefiere respuestas cortas"]
    assert "Prefiero respuestas cortas." in captured[0]
    assert "Calle Inventada" not in captured[0]
    assert "Adjuntos:" not in captured[0]
    assert module.store.list_memories() == []


def test_suggestions_with_no_user_statements_do_not_call_model(monkeypatch):
    module.store = ConversationStore(":memory:")
    module.store.put("example", [{"role": "assistant", "content": "Afirmación inventada"}])
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "admin")

    def unexpected():
        raise AssertionError("The router must not be contacted")

    monkeypatch.setattr(module, "get_backend", unexpected)
    response = TestClient(module.app).post(
        "/api/memories/suggest", json={"conversation_id": "example"}
    )
    assert response.status_code == 200
    assert response.json() == {"suggestions": []}
