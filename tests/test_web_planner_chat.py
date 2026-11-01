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
    # Semantic planning may condense the follow-up into an equivalent search query.
    # Do not require the literal chat wording: that would penalize better queries.
    assert "River Plate" in searches[1]
    assert "próximo partido" in searches[1]
    assert any("EVIDENCIA_WEB" in m["content"] for m in messages[-1])


def test_chat_exposes_only_actual_https_web_sources(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    monkeypatch.setattr(
        web_research, "web_evidence_with_pages",
        lambda query, **kwargs: (
            'Fecha de consulta: ahora. Datos EXTERNOS NO CONFIABLES en JSON:\\n'
            '[{"title":"Nota consultada","url":"https://example.com/noticia",'
            '"rss_snippet_unverified":"Texto no verificado"},'
            '{"title":"No es HTTPS","url":"http://example.com/inseguro"}]'
        ),
    )
    response = client.post("/api/chat", json={"text": "¿Cuándo es el próximo partido?"})
    assert response.status_code == 200
    assert response.json()["web_sources"] == [
        {"title": "Nota consultada", "url": "https://example.com/noticia", "evidence_type": "rss_snippet"}
    ]
    assert response.json()["answer"] == "Respuesta de prueba"


def test_google_account_conversational_probe_uses_one_answer_without_web(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    response = client.post("/api/chat", json={
        "text": "Probando si anda IAchat con mi cuenta de mail",
    })
    assert response.status_code == 200
    assert response.json()["answer"] == "Respuesta de prueba"
    assert response.json()["web_sources"] == []
    assert searches == []
    assert len(messages) == 1  # no extra LLM classifier call
    assert not any("DATOS DE HERRAMIENTA WEB" in m["content"] for m in messages[0])


def test_web_sources_and_response_time_survive_authenticated_history_reload(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    monkeypatch.setattr(
        web_research, "web_evidence_with_pages",
        lambda query, **kwargs: (
            'Fecha de consulta: ahora. Datos EXTERNOS NO CONFIABLES en JSON:\\n'
            '[{"title":"Noticia consultada","url":"https://example.com/noticia",'
            '"rss_snippet_unverified":"Datos externos"}]'
        ),
    )
    response = client.post("/api/chat", json={"text": "¿Cuándo juega River?"})
    assert response.status_code == 200
    data = response.json()
    last = data["history"][-1]
    assert last["web_sources"] == data["web_sources"]
    assert last["web_sources"][0]["url"] == "https://example.com/noticia"
    assert isinstance(last["elapsed_ms"], int) and last["elapsed_ms"] >= 0
    assert "T" in last["completed_at"]
    restored = client.get("/api/conversations/" + data["conversation_id"])
    assert restored.status_code == 200
    assert restored.json()["history"][-1] == last


def test_banal_probe_has_no_sources_even_after_reload(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    response = client.post("/api/chat", json={"text": "Probando si anda IAchat con mi cuenta de mail"})
    assert response.status_code == 200
    restored = client.get("/api/conversations/" + response.json()["conversation_id"])
    assert restored.status_code == 200
    assert restored.json()["history"][-1]["web_sources"] == []
    assert searches == []


def test_two_independent_questions_keep_evidence_separate(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    question = "¿Cuándo juega River y cuándo corre la Fórmula 1?"
    response = client.post("/api/chat", json={"text": question})
    assert response.status_code == 200
    assert searches == ["Cuándo juega River?", "cuándo corre la Fórmula 1?"]
    tool_message = next(
        m["content"] for call in messages for m in call
        if "DATOS DE HERRAMIENTA WEB" in m["content"]
    )
    assert "[EVIDENCIA PARA PREGUNTA 1: Cuándo juega River?]" in tool_message
    assert "[EVIDENCIA PARA PREGUNTA 2: cuándo corre la Fórmula 1?]" in tool_message
    assert tool_message.count("EVIDENCIA_WEB") == 2


def test_two_topics_show_both_sources_and_keep_all_ten_on_reload(monkeypatch):
    import json

    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)

    def fake_evidence(query, **kwargs):
        topic = "river" if "River" in query else "f1"
        return "Fecha de consulta: ahora. Datos EXTERNOS NO CONFIABLES en JSON:\n" + json.dumps([
            {
                "title": f"{topic} noticia {n}",
                "url": f"https://example.com/{topic}/{n}",
                "rss_snippet_unverified": "Noticia de prueba, no verificada",
            }
            for n in range(5)
        ])

    monkeypatch.setattr(web_research, "web_evidence_with_pages", fake_evidence)
    response = client.post("/api/chat", json={
        "text": "¿Cuándo juega River y cuándo corre la Fórmula 1?",
    })
    assert response.status_code == 200
    data = response.json()
    urls = [source["url"] for source in data["web_sources"]]
    assert len(urls) == 10
    # The UI shows the first three links; both questions must be represented.
    assert "/river/" in urls[0] and "/f1/" in urls[1]
    assert "/river/" in urls[2]
    restored = client.get("/api/conversations/" + data["conversation_id"])
    assert restored.status_code == 200
    assert restored.json()["history"][-1]["web_sources"] == data["web_sources"]


def test_semantic_web_rewrite_with_zero_sources_retries_original(monkeypatch):
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)

    class Rewriter:
        def answer(self, prompt):
            if prompt[0]["role"] == "system" and "clasificador" in prompt[0]["content"].lower():
                return '{"action":"search","query":"novedades institucionales ambiguas"}'
            messages.append(prompt)
            return "Respuesta de prueba con fuente"

    monkeypatch.setattr(app_module, "get_backend", lambda: Rewriter())

    def evidence(query, **kwargs):
        searches.append(query)
        if query == "novedades institucionales ambiguas":
            return "No hubo resultados disponibles."
        return ('Datos EXTERNOS NO CONFIABLES en JSON:\n'
                '[{"title":"Noticia","url":"https://example.com/anses",'
                '"rss_snippet_unverified":"Nota de prueba"}]')

    monkeypatch.setattr(web_research, "web_evidence_with_pages", evidence)
    question = "¿Cuáles son las novedades de ANSES de esta semana?"
    response = client.post("/api/chat", json={"text": question})
    assert response.status_code == 200
    assert searches == ["novedades institucionales ambiguas", question]
    assert response.json()["web_sources"][0]["url"] == "https://example.com/anses"


def test_day_later_broadcast_followup_uses_persisted_user_topic(monkeypatch):
    """The date gap must not change River-Boca into an unrelated event."""
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    app_module.store.put("river-day-old", [
        {"role": "user", "content": "¿Cuándo es el próximo River-Boca?"},
        {"role": "assistant", "content": "No pude confirmar la fecha.",
         "completed_at": "2026-10-31T16:00:00+00:00"},
    ], "admin", "")

    response = client.post("/api/chat", json={
        "conversation_id": "river-day-old",
        "text": "¿Y en qué canal lo pasan?",
    })
    assert response.status_code == 200
    assert len(searches) == 1
    assert "River-Boca" in searches[0]
    assert "Mundial" not in searches[0]
    assert "canal" in searches[0]

    confirmation = client.post("/api/chat", json={
        "conversation_id": "river-day-old",
        "text": "¿Lo pasan por Telefe?",
    })
    assert confirmation.status_code == 200
    assert len(searches) == 2
    assert "River-Boca" in searches[1]
    assert "Telefe" in searches[1]
    assert all("Mundial" not in query for query in searches)


def test_day_later_followup_after_channel_correction_keeps_event(monkeypatch):
    """Persisted user corrections must not erase the original search topic."""
    messages, searches = [], []
    client = _client(monkeypatch, messages, searches)
    app_module.store.put("river-corrected", [
        {"role": "user", "content": "¿Cuándo es el próximo River-Boca?"},
        {"role": "assistant", "content": "No confirmado.",
         "completed_at": "2026-10-30T16:00:00+00:00"},
        {"role": "user", "content": "¿Y en qué canal lo pasan?"},
        {"role": "assistant", "content": "Lo pasan por Telefe."},
        {"role": "user", "content": "No, Telefe no lo pasa."},
        {"role": "assistant", "content": "No puedo confirmar el canal."},
    ], "admin", "")

    response = client.post("/api/chat", json={
        "conversation_id": "river-corrected",
        "text": "¿Y el horario?",
    })
    assert response.status_code == 200
    assert len(searches) == 1
    assert "River-Boca" in searches[0]
    assert "Mundial" not in searches[0]
    assert "Telefe" not in searches[0]
