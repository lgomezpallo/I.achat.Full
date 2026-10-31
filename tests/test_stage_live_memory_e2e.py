"""Offline regressions for the isolated *real-provider* Oracle stage runner.

These checks do not substitute for the actual live stage workflow.
"""
from __future__ import annotations

from pathlib import Path
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
    store._db.close()
    assert verify_snapshot(path, "alice", "bob", "c", marker, 480)
    assert not verify_snapshot(path, "bob", "alice", "c", marker, 480)
    assert not verify_snapshot(path, "alice", "bob", "c", "WRONGMARKER", 480)

    reopened = ConversationStore(str(path))
    history = reopened.get("c", "alice")
    history.extend([
        {"role": "user", "content": "¿Cuál es la decisión final?"},
        {"role": "assistant", "content": "La respuesta se conservó."},
    ])
    reopened.put("c", history, "alice", "Atlas")
    reopened._db.close()
    assert verify_snapshot(path, "alice", "bob", "c", marker, 482)

    restored = tmp_path / "restored.sqlite3"
    backup_database(path, restored)
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    assert verify_snapshot(restored, "alice", "bob", "c", marker, 482)


def test_stage_never_inherits_router_or_billing_configuration():
    assert "ROUTER_TOKEN" not in ALLOWED_ENV
    assert "ROUTER_URL" not in ALLOWED_ENV
    assert "OPENAI_API_KEY" not in ALLOWED_ENV
    assert "STRIPE_SECRET_KEY" not in ALLOWED_ENV
    assert "GROQ_API_KEY" in ALLOWED_ENV
    assert "OPENROUTER_API_KEY" in ALLOWED_ENV
