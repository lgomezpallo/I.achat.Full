"""Regression: append-only memory protects hidden metadata and raw E2E integrity."""
from __future__ import annotations

import json
from pathlib import Path
from runpy import run_path
import sqlite3

import pytest

from iachat.store import ConversationStore

ROOT = Path(__file__).resolve().parents[1]
stage = run_path(str(ROOT / "scripts" / "stage_live_memory_e2e.py"))
probe = run_path(str(ROOT / "scripts" / "live_memory_probe.py"))
raw_transcript = stage["raw_transcript"]
transcript_fingerprint = stage["transcript_fingerprint"]
verify_snapshot = stage["verify_snapshot"]
seed_memory_probe = probe["seed_memory_probe"]


def test_append_preserves_existing_metadata_even_if_caller_replaces_it(tmp_path):
    path = tmp_path / "history.sqlite3"
    store = ConversationStore(str(path))
    original = [
        {"role": "user", "content": "Decidimos conservar el archivo original.",
         "attachments": [{"name": "evidencia-original.pdf", "sha256": "abc"}]},
        {"role": "assistant", "content": "Confirmado.",
         "model": "free-model",
         "web_sources": [{"url": "https://example.org/original"}]},
    ]
    store.put("conversation", original, "alice", "Atlas")
    baseline = transcript_fingerprint(raw_transcript(path, "alice", "conversation"), 2)

    # The public API filters fields such as model and attachment metadata.
    # An append must neither drop them nor accept forged replacements.
    stale_or_forged = [
        {"role": "user", "content": original[0]["content"],
         "attachments": [{"name": "reemplazado.pdf", "sha256": "def"}]},
        {"role": "assistant", "content": "Confirmado.",
         "model": "paid-model",
         "web_sources": [{"url": "https://example.org/altered"}],
         "new_field": "injected"},
        {"role": "user", "content": "Falta validar el respaldo."},
    ]
    store.put("conversation", stale_or_forged, "alice", "Atlas")
    saved = raw_transcript(path, "alice", "conversation")
    assert saved[:2] == original
    assert transcript_fingerprint(saved, 2) == baseline
    assert saved[2] == {"role": "user", "content": "Falta validar el respaldo."}
    assert store.get_summary("conversation", "alice")["processed_count"] == 3
    store._db.close()
    assert raw_transcript(path, "alice", "conversation") == saved


def test_e2e_detects_hidden_metadata_corruption_not_visible_in_public_get(tmp_path):
    path = tmp_path / "raw.sqlite3"
    store = ConversationStore(str(path))
    marker = "LUCERO12AB34CD"
    seed_memory_probe(store, "alice", "long", marker)
    original = raw_transcript(path, "alice", "long")
    baseline = transcript_fingerprint(original)
    assert verify_snapshot(path, "alice", "bob", "long", marker, 480, baseline)

    with sqlite3.connect(path) as db:
        changed = json.loads(db.execute(
            "SELECT history FROM conversations WHERE id='long'"
        ).fetchone()[0])
        changed[99]["model"] = "unexpected-model"
        db.execute("UPDATE conversations SET history=? WHERE id='long'",
                   (json.dumps(changed, ensure_ascii=False),))
    # The filtered getter intentionally hides model metadata.
    assert store.get("long", "alice") == [
        {"role": m["role"], "content": m["content"]} for m in original
    ]
    assert not verify_snapshot(path, "alice", "bob", "long", marker, 480, baseline)
    assert raw_transcript(path, "bob", "long") is None


def test_raw_reader_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        raw_transcript(missing, "alice", "none")
    assert not missing.exists()
