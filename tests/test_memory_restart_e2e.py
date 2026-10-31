"""HTTP/process-boundary memory regression with an isolated SQLite database.

Three independent Python interpreters seed a long transcript, resume through
authenticated FastAPI HTTP, and verify a private backup/restore. No network,
paid provider, production data, Oracle access or deployment is involved.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path
from runpy import run_path

phase, db_path, backup_path = sys.argv[1:]
if phase == "seed":
    from iachat.store import ConversationStore
    store = ConversationStore(db_path)
    assert store.create_user("alice", "test-only-alice-password")
    assert store.create_user("bob", "test-only-bob-password")
    history = []
    for index in range(240):
        if index == 0:
            statement = "Decidimos usar PostgreSQL para el proyecto Atlas."
        elif index == 100:
            statement = "Decidimos usar el motor Orión para el proyecto Violeta."
        elif index == 239:
            statement = "Corrijo: el respaldo del proyecto Atlas será diario."
        else:
            statement = f"Decidimos revisar la tarea general número {index}."
        history.extend([
            {"role": "user", "content": statement},
            {"role": "assistant", "content": "Respuesta ficticia; no es un recuerdo."},
        ])
    store.put("long-chat", history, "alice", "Atlas")
    store.save_automatic_memory("m1", "Prefiero respuestas breves", "alice", "Atlas")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE conversation_index SET updated_at=updated_at-21*86400 "
            "WHERE id=? AND owner=?", ("long-chat", "alice")
        )
    assert store.get_summary("long-chat", "alice")["processed_count"] == 480
    print("SEED=480_MESSAGES THREE_WEEKS_SIMULATED")
elif phase == "http":
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    import iachat.app as module
    import iachat.web_planner as web_planner
    from iachat.store import ConversationStore

    module.store = ConversationStore(db_path)
    web_planner.plan_web_lookup_semantic = lambda *a, **kw: SimpleNamespace(
        action="none", reason="offline_test", query=""
    )
    calls = []
    class OfflineBackend:
        def answer(self, messages, images=None):
            last = messages[-1]["content"]
            if "FALLA_SIMULADA" in last:
                raise RuntimeError("providers_unavailable")
            calls.append(messages)
            return "Respuesta de prueba sin proveedor real."

    module.get_backend = lambda: OfflineBackend()
    client = TestClient(module.app, base_url="https://testserver")
    login = client.post("/auth/login", json={
        "username": "alice", "password": "test-only-alice-password"
    })
    assert login.status_code == 200, login.text[:200]
    response = client.post("/api/chat", json={
        "conversation_id": "long-chat",
        "project": "Atlas",
        "text": "¿Qué motor elegimos para Violeta?",
    })
    assert response.status_code == 200, response.text[:200]
    assert len(response.json()["history"]) == 482
    # This decision was evicted from the 120-item compact ledger. Verify
    # actual model-input construction through the authenticated HTTP route.
    context = json.dumps(calls[-1], ensure_ascii=False)
    assert "motor Orión para el proyecto Violeta" in context
    assert "Respuesta ficticia; no es un recuerdo." not in context.split(
        "Citas originales del usuario recuperadas"
    )[-1].split("No inventes recuerdos ausentes:")[0]

    failed = client.post("/api/chat", json={
        "conversation_id": "long-chat",
        "project": "Atlas",
        "text": "FALLA_SIMULADA",
    })
    assert failed.status_code == 503, failed.text[:200]
    persisted = module.store.get("long-chat", "alice")
    assert len(persisted) == 483
    assert persisted[-1] == {"role": "user", "content": "FALLA_SIMULADA"}
    assert module.store.get_summary("long-chat", "alice")["processed_count"] == 483
    # The project boundary is checked before writing another user turn.
    mismatch = client.post("/api/chat", json={
        "conversation_id": "long-chat", "project": "Otro", "text": "Hola",
    })
    assert mismatch.status_code == 409
    assert len(module.store.get("long-chat", "alice")) == 483
    other = TestClient(module.app, base_url="https://testserver")
    assert other.post("/auth/login", json={
        "username": "bob", "password": "test-only-bob-password"
    }).status_code == 200
    assert other.get("/api/conversations/long-chat").status_code == 404
    assert other.get("/api/memories").json()["memories"] == []
    print("AUTHENTICATED_HTTP=PASS RECALL_MIDDLE=PASS PROVIDER_FAILURE=503 "
          "PENDING_TURN_PERSISTED=PASS OWNER_PROJECT_ISOLATION=PASS")
elif phase == "restore":
    from iachat.store import ConversationStore
    from iachat.conversation_summary import render_summary, render_archived_evidence
    store = ConversationStore(db_path)
    original = store.get("long-chat", "alice")
    assert len(original) == 483
    assert original[-1]["content"] == "FALLA_SIMULADA"
    assert store.get("long-chat", "bob") is None
    backup_database = run_path(
        str(Path("scripts/backup_iachat_db.py").resolve())
    )["backup_database"]
    backup_database(Path(db_path), Path(backup_path))
    assert stat.S_IMODE(Path(backup_path).stat().st_mode) == 0o600
    restored = ConversationStore(backup_path)
    assert restored.get("long-chat", "alice") == original
    assert restored.get("long-chat", "bob") is None
    summary = restored.get_summary("long-chat", "alice")
    assert summary["processed_count"] == 483
    assert len(summary["items"]) == 120
    question = "¿Qué motor elegimos para Violeta?"
    context = render_summary(summary, question=question) + render_archived_evidence(
        original, summary, question
    )
    assert "motor Orión para el proyecto Violeta" in context
    assert restored.list_memories("alice", "Atlas")[0]["content"] == "Prefiero respuestas breves"
    assert restored.list_memories("alice", "Otro") == []
    assert restored.list_memories("bob") == []
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("RESTART=PASS BACKUP_RESTORE=PASS MEMORY_RECALL=PASS "
          "SQLITE_INTEGRITY=PASS PROVIDER_LIVE=NOT_RUN ORACLE=NOT_RUN")
else:
    raise AssertionError("unknown_test_phase")
'''


def test_authenticated_memory_survives_process_restart_provider_failure_and_backup(tmp_path):
    db_path = tmp_path / "live.sqlite3"
    backup_path = tmp_path / "backup.sqlite3"
    env = {
        **os.environ,
        "IACHAT_DB": str(db_path),
        "IACHAT_AUTH_SECRET": "local-test-only-signing-secret",
        "IACHAT_BACKEND": "integrated",
    }
    for phase in ("seed", "http", "restore"):
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(CHILD),
             phase, str(db_path), str(backup_path)],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=100,
            check=False,
        )
        assert result.returncode == 0, (
            f"{phase} failed (exit={result.returncode}): "
            f"{result.stdout[-1500:]} {result.stderr[-3000:]}"
        )
        assert "PASS" in result.stdout or phase == "seed", result.stdout
