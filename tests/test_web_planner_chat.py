"""Offline integration tests for contextual web planning in the chat flow."""
from fastapi.testclient import TestClient

from iachat import app as app_module
from iachat import web_research
from iachat.store import ConversationStore


def _client(monkeypatch, captured, searches):
    app_module.store = ConversationStore(":memory:")
    monkeypatch.setattr(app_module, "_signed_user", lambda cookie: "admin")

    class Backend:
        def answer(self, messages):
            captured.append(messages)
            return "Respuesta de prueba"

    monkeypatch.setattr(app_module, "get_backend", lambda: Backend())
    monkeypatch.setattr(
        web_research, "web_evidence_with_pages",
        lambda query, **kwargs: searches.append(query) or "EVIDENCIA_WEB",
    )
    return TestClient(app_module.app, base_url="https://testserver")


def test_explicit_documentation_search_reaches_evidence(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    response = client.post("/api/chat", json={"text": "Buscá documentación de FastAPI"})
    assert response.status_code == 200
    assert searches == ["Buscá documentación de FastAPI"]
    assert any("EVIDENCIA_WEB" in msg["content"] for msg in messages[0])


def test_referential_followup_keeps_subject_without_assistant_text(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    first = client.post("/api/chat", json={"text": "¿Cuándo juega River?"})
    assert first.status_code == 200
    cid = first.json()["conversation_id"]
    second = client.post("/api/chat", json={
        "text": "¿Y dónde lo pasan?", "conversation_id": cid,
    })
    assert second.status_code == 200
    assert len(searches) == 2
    assert "River" in searches[1]
    assert "dónde lo pasan" in searches[1]
    assert "Respuesta de prueba" not in searches[1]
    assert any("EVIDENCIA_WEB" in msg["content"] for msg in messages[1])


def test_topic_change_does_not_reuse_stale_web_intent(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    first = client.post("/api/chat", json={"text": "¿Cuándo juega River?"})
    cid = first.json()["conversation_id"]
    assert client.post("/api/chat", json={
        "text": "Explicá qué es una variable", "conversation_id": cid,
    }).status_code == 200
    assert client.post("/api/chat", json={
        "text": "¿Y dónde?", "conversation_id": cid,
    }).status_code == 200
    assert len(searches) == 1


def test_non_current_question_stays_offline(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    response = client.post("/api/chat", json={"text": "Explicá el ciclo del agua"})
    assert response.status_code == 200
    assert searches == []


def test_short_clarification_triggers_real_chat_web_path(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)

    class ClarifyingBackend:
        def answer(self, prompt):
            if prompt[0]["role"] == "system" and "clasificador" in prompt[0]["content"].lower():
                return '{"action":"search","query":"River Plate próximo partido"}'
            messages.append(prompt)
            return ("¿A qué entidad te referís?" if len(messages) == 1
                    else "Respuesta de prueba")

    monkeypatch.setattr(app_module, "get_backend", lambda: ClarifyingBackend())
    first = client.post("/api/chat", json={"text": "¿Cuándo juega River?"})
    assert first.status_code == 200
    second = client.post("/api/chat", json={
        "text": "River Plate.", "conversation_id": first.json()["conversation_id"],
    })
    assert second.status_code == 200
    assert len(searches) == 2
    assert "River Plate." in searches[1]
    assert "¿Cuándo juega River?" in searches[1]
    assert any("EVIDENCIA_WEB" in m["content"] for m in messages[-1])
