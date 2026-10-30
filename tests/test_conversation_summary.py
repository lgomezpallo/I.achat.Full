"""Persistence, provenance and long-conversation regression for the summary ledger."""
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import iachat.app as module
from iachat.conversation_summary import build_summary, render_summary
from iachat.store import ConversationStore


def test_summary_only_quotes_explicit_user_statements():
    history = [
        {"role": "assistant", "content": "Decidimos usar una clave secreta."},
        {"role": "user", "content": "Decidimos usar SQLite para IAchat."},
        {"role": "user", "content": "Tengo una bicicleta plegable verde."},
        {"role": "user", "content": "Falta probar la recuperación después del reinicio."},
        {"role": "user", "content": "Corrijo: la bicicleta es azul."},
        {"role": "user", "content": "Mi contraseña es supersecreta."},
        {"role": "user", "content": "Decidimos guardar un archivo.\nAdjuntos: clave.pdf"},
    ]
    summary = build_summary(history)
    quotes = [item["quote"] for item in summary["items"]]
    assert len(quotes) == 4
    assert "Decidimos usar SQLite para IAchat." in quotes
    assert "Corrijo: la bicicleta es azul." in quotes
    assert all("contraseña" not in quote for quote in quotes)
    assert all(item["source_index"] in (1, 2, 3, 4) for item in summary["items"])
    rendered = render_summary(summary)
    assert "mensaje 1" in rendered
    assert "Decidimos usar una clave" not in rendered


def test_incremental_summary_is_versioned_and_survives_reopen(tmp_path):
    path = str(tmp_path / "memory.db")
    store = ConversationStore(path)
    history = [
        {"role": "user", "content": "Decidimos usar SQLite para el historial."},
        {"role": "assistant", "content": "Confirmado."},
    ]
    store.put("conversation", history, "alice", "IAchat")
    first = store.get_summary("conversation", "alice")
    assert first["version"] == 1
    assert first["processed_count"] == 2
    store.put("conversation", history, "alice", "IAchat")
    assert store.get_summary("conversation", "alice")["version"] == 1
    history += [
        {"role": "user", "content": "Falta verificar los backups."},
        {"role": "assistant", "content": "Pendiente."},
    ]
    store.put("conversation", history, "alice", "IAchat")
    reopened = ConversationStore(path)
    summary = reopened.get_summary("conversation", "alice")
    assert summary["version"] == 2
    assert summary["processed_count"] == 4
    assert [item["source_index"] for item in summary["items"]] == [0, 2]
    assert len(reopened.get("conversation", "alice")) == 4
    assert reopened.get_summary("conversation", "bob") is None
    assert reopened.get("conversation", "bob") is None
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT count(*) FROM conversation_summary_versions "
            "WHERE owner='alice' AND conversation_id='conversation'"
        ).fetchone()[0] == 2


def test_nonappend_writes_cannot_destroy_transcript(tmp_path):
    store = ConversationStore(str(tmp_path / "guard.db"))
    original = [
        {"role": "user", "content": "Decidimos conservar todo el historial."},
        {"role": "assistant", "content": "OK", "elapsed_ms": 50},
    ]
    store.put("c", original, "alice")
    with pytest.raises(ValueError, match="conversation_history_conflict"):
        store.put("c", [{"role": "user", "content": "Otro tema"}], "alice")
    with pytest.raises(ValueError, match="conversation_history_conflict"):
        store.put("c", original[:1], "alice")
    with pytest.raises(ValueError, match="conversation_owner_mismatch"):
        store.put("c", original, "bob")
    assert store.get("c", "alice") == original
    assert store.get_summary("c", "alice")["version"] == 1
    # Clients omitting old response metadata cannot accidentally erase it.
    store.put("c", [
        {"role": "user", "content": original[0]["content"]},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": "Falta probar reinicio."},
    ], "alice")
    assert store.get("c", "alice")[1]["elapsed_ms"] == 50


def test_long_conversation_recalls_start_middle_end_without_assistant_fabrications(monkeypatch, tmp_path):
    path = str(tmp_path / "long.db")
    module.store = ConversationStore(path)
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args: SimpleNamespace(action="skip"),
    )
    history = []
    for index in range(160):
        if index == 0:
            user_text = "Decidimos usar PostgreSQL para el proyecto Atlas."
        elif index == 75:
            user_text = "Falta revisar el respaldo semanal del proyecto Atlas."
        elif index == 159:
            user_text = "Corrijo: el respaldo del proyecto Atlas será diario."
        else:
            user_text = f"Conversación de relleno {index}."
        history.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": "Respuesta de prueba, no es memoria."},
        ])
    module.store.put("long", history, "alice", "Atlas")
    # Simulate 21 days of inactivity, then a fresh process opening the same DB.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE conversation_index SET updated_at=updated_at-21*86400 WHERE id=?", ("long",))
    module.store = ConversationStore(path)
    captured = []

    class Backend:
        def answer(self, messages):
            captured.extend(messages)
            return "Respuesta de prueba"

    monkeypatch.setattr(module, "get_backend", lambda: Backend())
    result = TestClient(module.app).post(
        "/api/chat",
        json={"conversation_id": "long", "project": "Atlas",
              "text": "¿Qué habíamos decidido y qué quedó pendiente?"},
    )
    assert result.status_code == 200
    assert len(result.json()["history"]) == 322
    context = "\n".join(m["content"] for m in captured if m["role"] == "system")
    assert "Decidimos usar PostgreSQL para el proyecto Atlas." in context
    assert "Falta revisar el respaldo semanal del proyecto Atlas." in context
    assert "Corrijo: el respaldo del proyecto Atlas será diario." in context
    assert "Respuesta de prueba, no es memoria." not in context
    assert module.store.get_summary("long", "alice")["version"] == 2
    assert module.store.get_summary("long", "bob") is None


def test_stale_writer_from_second_process_cannot_erase_turns(tmp_path):
    path = str(tmp_path / "multi-process.db")
    first = ConversationStore(path)
    second = ConversationStore(path)
    initial = [
        {"role": "user", "content": "Decidimos guardar todas las respuestas."},
        {"role": "assistant", "content": "OK"},
    ]
    first.put("shared", initial, "alice")
    stale = second.get("shared", "alice")
    first.put("shared", [
        *initial,
        {"role": "user", "content": "Falta comprobar persistencia."},
        {"role": "assistant", "content": "OK"},
    ], "alice")
    with pytest.raises(ValueError, match="conversation_history_conflict"):
        second.put("shared", [
            *stale,
            {"role": "user", "content": "Corrijo: otro texto."},
            {"role": "assistant", "content": "OK"},
        ], "alice")
    assert len(ConversationStore(path).get("shared", "alice")) == 4
    assert first.get_summary("shared", "alice")["version"] == 2


def test_provider_failure_does_not_advance_summary_or_history(monkeypatch, tmp_path):
    module.store = ConversationStore(str(tmp_path / "failed.db"))
    module.store.put("c", [
        {"role": "user", "content": "Decidimos usar memoria duradera."},
        {"role": "assistant", "content": "Entendido."},
    ], "alice", "IAchat")
    monkeypatch.setattr(module, "_signed_user", lambda cookie: "alice")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args: SimpleNamespace(action="skip"),
    )

    class BrokenBackend:
        def answer(self, messages):
            raise RuntimeError("providers_unavailable")

    monkeypatch.setattr(module, "get_backend", lambda: BrokenBackend())
    response = TestClient(module.app).post(
        "/api/chat",
        json={"conversation_id": "c", "project": "IAchat", "text": "Falta verificar el backup."},
    )
    assert response.status_code == 503
    assert module.store.get_summary("c", "alice")["version"] == 1
    assert len(module.store.get("c", "alice")) == 2


def test_long_ledger_keeps_original_decision_and_latest_change():
    history = [
        {"role": "user", "content": (
            "Decidimos empezar con el plan inicial del proyecto."
            if index == 0 else
            f"Decidimos revisar el tema número {index} del proyecto."
        )}
        for index in range(180)
    ]
    history.append({"role": "user", "content": "Corrijo: el plan del proyecto ahora es semanal."})
    summary = build_summary(history)
    assert len(summary["items"]) == 120
    assert summary["items"][0]["source_index"] == 0
    assert summary["items"][-1]["source_index"] == 180
    rendered = render_summary(summary)
    assert "plan inicial del proyecto" in rendered
    assert "Corrijo: el plan del proyecto ahora es semanal." in rendered
    assert "tema número 179" in rendered
    # The incremental path must not discard the original anchor on append.
    summary2 = build_summary(
        history + [{"role": "user", "content": "Falta validar el plan semanal."}],
        summary,
    )
    assert summary2["items"][0]["source_index"] == 0
    assert summary2["items"][-1]["source_index"] == 181


def test_bounded_summary_prioritizes_late_correction_over_old_quotes():
    history = [
        {"role": "user", "content": "Decidimos comenzar con el plan original."},
        *[
            {"role": "user", "content": f"Decidimos trabajar sobre la variante {i} del proyecto."}
            for i in range(50)
        ],
        {"role": "user", "content": "Corrijo: la variante final del proyecto es azul."},
    ]
    rendered = render_summary(build_summary(history), max_chars=520)
    assert len(rendered) <= 520
    assert "plan original" in rendered
    assert "Corrijo: la variante final del proyecto es azul." in rendered
    assert "variante 49" in rendered
    assert render_summary(build_summary(history), max_chars=100) == ""
