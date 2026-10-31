"""Fail-closed memory recovery from the owner-scoped immutable transcript."""
from __future__ import annotations

import json
import sqlite3

from iachat.store import ConversationStore
from iachat.conversation_summary import render_summary


def _seed(tmp_path):
    store = ConversationStore(str(tmp_path / "integrity.sqlite3"))
    original = [{"role": "user", "content": "Decidimos usar SQLite para Atlas."}]
    store.put("chat", original, "alice", "Atlas")
    return store, original


def test_modified_transcript_never_returns_stale_summary(tmp_path):
    store, original = _seed(tmp_path)
    checkpoint = store._db.execute(
        "SELECT summary_json FROM conversation_summary_versions "
        "WHERE owner='alice' AND conversation_id='chat'"
    ).fetchone()[0]
    corrected = [{"role": "user", "content": "Corrijo: usaremos PostgreSQL para Atlas."}]
    store._db.execute(
        "UPDATE conversations SET history=? WHERE id='chat' AND owner='alice'",
        (json.dumps(corrected),),
    )
    store._db.commit()
    recovered = store.get_summary("chat", "alice")
    assert recovered["integrity_rebuilt"] is True
    evidence = render_summary(recovered)
    assert "PostgreSQL" in evidence
    assert "Decidimos usar SQLite" not in evidence
    assert store._db.execute(
        "SELECT summary_json FROM conversation_summary_versions "
        "WHERE owner='alice' AND conversation_id='chat'"
    ).fetchone()[0] == checkpoint
    assert store.get_summary("chat", "bob") is None
    store._db.close()


def test_fabricated_summary_quote_with_valid_prefix_hash_is_rejected(tmp_path):
    store, original = _seed(tmp_path)
    previous = store.get_summary("chat", "alice")
    fake = {k: previous[k] for k in
            ("format_version", "processed_count", "prefix_hash", "items")}
    fake["items"] = [{
        "kind": "decisión", "source_index": 0,
        "quote": "Decidimos usar un proveedor pago para Atlas."
    }]
    store._db.execute(
        "UPDATE conversation_summary_state SET summary_json=? "
        "WHERE owner='alice' AND conversation_id='chat'",
        (json.dumps(fake),),
    )
    store._db.commit()
    recovered = store.get_summary("chat", "alice")
    assert recovered["integrity_rebuilt"] is True
    assert "proveedor pago" not in render_summary(recovered)
    assert "SQLite para Atlas" in render_summary(recovered)
    store._db.close()


def test_corrupt_cursor_is_rebuilt_and_next_append_repairs_version(tmp_path):
    store, original = _seed(tmp_path)
    store._db.execute(
        "UPDATE conversation_summary_state SET summary_json='{invalid-json' "
        "WHERE owner='alice' AND conversation_id='chat'"
    )
    store._db.commit()
    recovered = store.get_summary("chat", "alice")
    assert recovered["integrity_rebuilt"] is True
    assert recovered["processed_count"] == 1
    history = original + [
        {"role": "assistant", "content": "Entendido."},
        {"role": "user", "content": "Corrijo: el respaldo será diario."},
    ]
    store.put("chat", history, "alice", "Atlas")
    repaired = store.get_summary("chat", "alice")
    assert "integrity_rebuilt" not in repaired
    assert repaired["version"] == 2
    assert repaired["processed_count"] == 3
    assert len(store.get("chat", "alice")) == 3
    store._db.close()


def test_restore_preserves_rebuilt_evidence_without_rewriting_audit(tmp_path):
    store, original = _seed(tmp_path)
    store._db.execute(
        "UPDATE conversation_summary_state SET summary_json=? "
        "WHERE owner='alice' AND conversation_id='chat'",
        (json.dumps({"format_version": 2, "processed_count": 1,
                     "prefix_hash": "fake", "items": []}),),
    )
    store._db.commit()
    backup = tmp_path / "restored.sqlite3"
    with sqlite3.connect(backup) as target:
        store._db.backup(target)
    restored = ConversationStore(str(backup))
    summary = restored.get_summary("chat", "alice")
    assert summary["integrity_rebuilt"] is True
    assert "SQLite para Atlas" in render_summary(summary)
    assert restored.get("chat", "alice") == original
    assert restored.get_summary("chat", "bob") is None
    store._db.close()
    restored._db.close()


def test_invalid_incremental_cursor_types_do_not_block_durable_append(tmp_path):
    store, original = _seed(tmp_path)
    invalid = {"format_version": 2, "processed_count": "one",
               "prefix_hash": "invalid", "items": [{"source_index": "zero"}]}
    store._db.execute(
        "UPDATE conversation_summary_state SET summary_json=? "
        "WHERE owner='alice' AND conversation_id='chat'",
        (json.dumps(invalid),),
    )
    store._db.commit()
    history = original + [
        {"role": "user", "content": "Corrijo: usaremos PostgreSQL para Atlas."}
    ]
    store.put("chat", history, "alice", "Atlas")
    summary = store.get_summary("chat", "alice")
    assert "integrity_rebuilt" not in summary
    assert summary["version"] == 2
    assert summary["processed_count"] == 2
    assert "PostgreSQL" in render_summary(summary)
    assert store.get("chat", "alice") == history
    store._db.close()
