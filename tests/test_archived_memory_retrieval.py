"""Regression: long-term recall of ledger-evicted, source-backed decisions."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import iachat.app as module
from iachat.conversation_summary import (
    build_summary, render_archived_evidence,
)
from iachat.store import ConversationStore


def _history():
    history = []
    for i in range(240):
        text = (
            "Decidimos usar el motor Orión para el proyecto Violeta."
            if i == 80 else f"Decidimos revisar la tarea genérica número {i}."
        )
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": "Respuesta no verificable."})
    return history


def test_archived_middle_decision_recovered_with_provenance_and_budget():
    history = _history()
    summary = build_summary(history)
    assert len(summary["items"]) == 120
    assert 160 not in {item["source_index"] for item in summary["items"]}
    result = render_archived_evidence(
        history, summary, "¿Qué motor elegimos para Violeta?", max_chars=450
    )
    assert "motor Orión" in result
    assert "mensaje 160" in result
    assert len(result) <= 450
    assert "Respuesta no verificable" not in result
    assert render_archived_evidence(history, summary, "¿Qué telescopio hay en Marte?") == ""


def test_archived_correction_and_sensitive_messages():
    history = _history()
    history[2] = {"role": "user", "content": "Corrijo: el plan general será mensual."}
    history[162] = {"role": "user", "content": "Corrijo: el motor de Violeta será solar."}
    history[164] = {"role": "user", "content": "Decidimos guardar el token privado de Violeta."}
    summary = build_summary(history)
    assert 162 not in {item["source_index"] for item in summary["items"]}
    result = render_archived_evidence(history, summary, "¿Qué motor usa Violeta?")
    assert "será solar" in result
    assert "token privado" not in result
    assert result.index("motor Orión") < result.index("será solar")


def test_archived_recall_reaches_chat_backend_after_reopening_db(monkeypatch, tmp_path):
    path = str(tmp_path / "archived.db")
    initial = ConversationStore(path)
    initial.put("long", _history(), "alice", "Violeta")
    module.store = ConversationStore(path)
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args: SimpleNamespace(action="skip"),
    )
    captured = []

    class Backend:
        def answer(self, messages):
            captured.extend(messages)
            return "Respuesta simulada"

    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    response = TestClient(module.app).post(
        "/api/chat",
        json={
            "conversation_id": "long", "project": "Violeta",
            "text": "¿Qué motor elegimos para Violeta?",
        },
    )
    assert response.status_code == 200
    system_text = "\n".join(m["content"] for m in captured if m["role"] == "system")
    assert "omitidas del resumen compacto" in system_text
    assert "motor Orión" in system_text
    assert "mensaje 160" in system_text
    assert module.store.get_summary("long", "bob") is None
    assert len(module.store.get("long", "alice")) == 482
