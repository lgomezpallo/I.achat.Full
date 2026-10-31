"""Fault-injection regressions for durable memory and private SQLite backups.

These are local database tests, not live-provider or Oracle E2E tests.
"""
import sqlite3
import stat
from pathlib import Path
from runpy import run_path

import pytest

from iachat.store import ConversationStore

# scripts/ is a deployment artifact, not an installed Python package.
backup_database = run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "backup_iachat_db.py"))["backup_database"]


def test_failed_automatic_memory_audit_rolls_back_and_does_not_poison_chat(tmp_path):
    path = tmp_path / "memory.db"
    store = ConversationStore(str(path))
    store._db.execute(
        "CREATE TRIGGER reject_new_audit BEFORE INSERT ON automatic_memory_log "
        "BEGIN SELECT RAISE(FAIL, 'audit_write_failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="audit_write_failed"):
        store.save_automatic_memory("m1", "Prefiero respuestas breves", "alice", "IAchat")

    assert not store._db.in_transaction
    assert store.list_memories("alice") == []
    assert store.list_automatic_memory_log("alice") == []
    store.put("c1", [{"role": "user", "content": "Decidimos guardar todo."}], "alice", "IAchat")
    reopened = ConversationStore(str(path))
    assert len(reopened.get("c1", "alice")) == 1
    assert reopened.get_summary("c1", "alice")["processed_count"] == 1
    assert reopened.list_memories("alice") == []


def test_failed_correction_audit_rolls_back_memory_change(tmp_path):
    path = tmp_path / "correction.db"
    store = ConversationStore(str(path))
    store.save_automatic_memory("m1", "Me gustan las series oscuras", "alice", "Cine")
    store._db.execute(
        "CREATE TRIGGER reject_correction BEFORE INSERT ON automatic_memory_log "
        "WHEN NEW.previous_content IS NOT NULL "
        "BEGIN SELECT RAISE(FAIL, 'correction_audit_failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="correction_audit_failed"):
        store.replace_automatic_memory(
            "m1", "Me gustan las series oscuras", "No me gustan las series oscuras",
            "alice", "Cine",
        )
    assert not store._db.in_transaction
    reopened = ConversationStore(str(path))
    assert reopened.list_memories("alice", "Cine")[0]["content"] == "Me gustan las series oscuras"
    assert len(reopened.list_automatic_memory_log("alice")) == 1


def test_failed_undo_audit_rolls_back_memory_deletion(tmp_path):
    path = tmp_path / "undo.db"
    store = ConversationStore(str(path))
    store.save_automatic_memory("m1", "Prefiero respuestas cortas", "alice", "IAchat")
    event = store.list_automatic_memory_log("alice")[0]
    store._db.execute(
        "CREATE TRIGGER reject_undo BEFORE UPDATE OF undone ON automatic_memory_log "
        "BEGIN SELECT RAISE(FAIL, 'undo_audit_failed'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="undo_audit_failed"):
        store.undo_automatic_memory(event["id"], "alice")
    assert not store._db.in_transaction
    reopened = ConversationStore(str(path))
    assert reopened.list_memories("alice", "IAchat")[0]["content"] == "Prefiero respuestas cortas"
    assert reopened.list_automatic_memory_log("alice")[0]["undone"] is False


def test_online_backup_is_private_and_restores_transcript_images_and_memory(tmp_path):
    live, backup = tmp_path / "live.db", tmp_path / "snapshot.db"
    store = ConversationStore(str(live))
    history = [{"role": "user", "content": "Decidimos conservar el historial completo."}]
    store.put(
        "chat", history, "alice", "IAchat",
        image_attachments=[("prueba.png", "data:image/png;base64,AA==")],
    )
    store.save_automatic_memory("m1", "Prefiero respuestas breves", "alice", "IAchat")

    backup_database(live, backup)

    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    restored = ConversationStore(str(backup))
    assert restored.get("chat", "alice") == history
    assert restored.get("chat", "bob") is None
    assert restored.get_summary("chat", "alice")["processed_count"] == 1
    assert restored.images_for_conversation("chat", "alice")[0]["filename"] == "prueba.png"
    assert restored.list_memories("alice", "IAchat")[0]["content"] == "Prefiero respuestas breves"
    assert len(restored.list_automatic_memory_log("alice")) == 1
    with sqlite3.connect(str(backup)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    with pytest.raises(FileExistsError):
        backup_database(live, backup)
    assert restored.get("chat", "alice") == history


def test_online_backup_refuses_symlink_destination(tmp_path):
    live = tmp_path / "live.db"
    store = ConversationStore(str(live))
    store.put("chat", [{"role": "user", "content": "Guardar datos"}], "alice")
    outside = tmp_path / "outside.db"
    destination = tmp_path / "snapshot.db"
    destination.symlink_to(outside)
    with pytest.raises(FileExistsError):
        backup_database(live, destination)
    assert destination.is_symlink()
    assert not outside.exists()


def test_online_backup_in_wal_mode_includes_committed_memory_not_uncommitted_edits(tmp_path):
    """A live WAL snapshot must be transaction-consistent across all memory tables."""
    live, backup = tmp_path / "wal-live.sqlite3", tmp_path / "wal-snapshot.sqlite3"
    store = ConversationStore(str(live))
    assert store._db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    history = [{"role": "user", "content": "Decidimos mantener la memoria íntegra."}]
    store.put(
        "chat", history, "alice", "Atlas",
        image_attachments=[("plano.png", "data:image/png;base64,AA==")],
    )
    store.save_automatic_memory("stable", "Prefiero respuestas claras", "alice", "Atlas")

    # Keep a writer transaction open while the online backup reads a coherent
    # snapshot. The attempted deletion must never appear in the backup.
    writer = sqlite3.connect(live, timeout=5)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE conversations SET history='[]' WHERE id='chat'")
    writer.execute("DELETE FROM memories WHERE id='stable'")
    try:
        backup_database(live, backup)
    finally:
        writer.rollback()
        writer.close()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    restored = ConversationStore(str(backup))
    assert restored.get("chat", "alice") == history
    assert restored.get("chat", "bob") is None
    assert restored.get_summary("chat", "alice")["processed_count"] == 1
    assert [i["filename"] for i in restored.images_for_conversation("chat", "alice")] == [
        "plano.png"
    ]
    assert restored.list_memories("alice", "Atlas")[0]["content"] == "Prefiero respuestas claras"
    assert len(restored.list_automatic_memory_log("alice")) == 1
    with sqlite3.connect(backup) as check:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    restored._db.close()
    store._db.close()
