"""Offline regressions for the isolated *real-provider* Oracle stage runner.

These checks do not substitute for the actual live stage workflow.
"""
from __future__ import annotations

from pathlib import Path
import json
import sqlite3
from runpy import run_path
import stat

from iachat.store import ConversationStore

ROOT = Path(__file__).resolve().parent.parent
stage = run_path(str(ROOT / "scripts" / "stage_live_memory_e2e.py"))
probe = run_path(str(ROOT / "scripts" / "live_memory_probe.py"))
backup = run_path(str(ROOT / "scripts" / "backup_iachat_db.py"))
ALLOWED_ENV = stage["ALLOWED_ENV"]
recall_flags = stage["recall_flags"]
verify_snapshot = stage["verify_snapshot"]
transcript_fingerprint = stage["transcript_fingerprint"]
seed_memory_probe = probe["seed_memory_probe"]
backup_database = backup["backup_database"]


def test_stage_checks_three_independent_answer_facts():
    marker = "LUCERO12AB34CD"
    assert recall_flags(
        "Base PostgreSQL; motor LUCERO12AB34CD; respaldo diario.", marker
    ) == (True, True, True)
    assert recall_flags(
        "Base PostgreSQL; motor desconocido; respaldo diario.", marker
    ) == (True, False, True)
    assert recall_flags("No recuerdo los datos.", marker) == (False, False, False)


def test_stage_reopens_and_restores_full_480_turn_history(tmp_path):
    path = tmp_path / "isolated.sqlite3"
    marker = "LUCERO12AB34CD"
    store = ConversationStore(str(path))
    seed_memory_probe(store, "alice", "c", marker)
    baseline = transcript_fingerprint(store.get("c", "alice"))
    store._db.close()
    assert verify_snapshot(path, "alice", "bob", "c", marker, 480, baseline)
    assert not verify_snapshot(path, "bob", "alice", "c", marker, 480)
    assert not verify_snapshot(path, "alice", "bob", "c", "WRONGMARKER", 480)

    reopened = ConversationStore(str(path))
    history = reopened.get("c", "alice")
    history.extend([
        {"role": "user", "content": "¿Cuál es la decisión final?"},
        {"role": "assistant", "content": "La respuesta se conservó."},
    ])
    reopened.put("c", history, "alice", "Atlas")
    full_hash = transcript_fingerprint(reopened.get("c", "alice"), 482)
    reopened._db.close()
    assert verify_snapshot(path, "alice", "bob", "c", marker, 482, baseline, full_hash)

    restored = tmp_path / "restored.sqlite3"
    backup_database(path, restored)
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    assert verify_snapshot(restored, "alice", "bob", "c", marker, 482, baseline, full_hash)

    # A three-anchor check alone would miss silent corruption at message 99.
    # Corrupt the restored copy, not the original, to prove full-prefix
    # fingerprinting detects an otherwise plausible transcript.
    with sqlite3.connect(restored) as db:
        history = json.loads(db.execute(
            "SELECT history FROM conversations WHERE id='c'"
        ).fetchone()[0])
        history[99]["content"] = "Contenido alterado sin tocar los tres anclajes"
        db.execute("UPDATE conversations SET history=? WHERE id='c'",
                   (json.dumps(history, ensure_ascii=False),))
    assert not verify_snapshot(restored, "alice", "bob", "c", marker, 482, baseline)
    assert verify_snapshot(path, "alice", "bob", "c", marker, 482, baseline, full_hash)

    # A complete digest must also detect corruption of the newly appended answer.
    restored_tail = tmp_path / "restored_tail.sqlite3"
    backup_database(path, restored_tail)
    with sqlite3.connect(restored_tail) as db:
        tail = json.loads(db.execute(
            "SELECT history FROM conversations WHERE id='c'"
        ).fetchone()[0])
        tail[481]["content"] = "Respuesta alterada tras la inferencia"
        db.execute("UPDATE conversations SET history=? WHERE id='c'",
                   (json.dumps(tail, ensure_ascii=False),))
    assert verify_snapshot(restored_tail, "alice", "bob", "c", marker, 482, baseline)
    assert not verify_snapshot(restored_tail, "alice", "bob", "c", marker, 482,
                               baseline, full_hash)


def test_fingerprint_covers_metadata_and_message_order():
    messages = [
        {"role": "user", "content": "inicio", "attachments": [{"name": "plano.pdf"}]},
        {"role": "assistant", "content": "recibido", "model": "free-model"},
    ]
    original = transcript_fingerprint(messages, 2)
    import copy
    changed = copy.deepcopy(messages)
    changed[0]["attachments"][0]["name"] = "otro.pdf"
    assert transcript_fingerprint(changed, 2) != original
    changed = copy.deepcopy(messages)
    changed[1]["model"] = "different-model"
    assert transcript_fingerprint(changed, 2) != original
    assert transcript_fingerprint(list(reversed(messages)), 2) != original


def test_stage_never_inherits_router_or_billing_configuration():
    assert "ROUTER_TOKEN" not in ALLOWED_ENV
    assert "ROUTER_URL" not in ALLOWED_ENV
    assert "OPENAI_API_KEY" not in ALLOWED_ENV
    assert "STRIPE_SECRET_KEY" not in ALLOWED_ENV
    assert "GROQ_API_KEY" in ALLOWED_ENV
    assert "OPENROUTER_API_KEY" in ALLOWED_ENV
