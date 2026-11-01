"""Durability regressions: immutable evidence checkpoints and a separate scan cursor."""
from __future__ import annotations

import json
import sqlite3

import pytest

from iachat.store import ConversationStore


def _checkpoints(db: sqlite3.Connection, owner: str = "alice", chat: str = "c"):
    return db.execute(
        "SELECT version, summary_json FROM conversation_summary_versions "
        "WHERE owner=? AND conversation_id=? ORDER BY version", (owner, chat)
    ).fetchall()


def test_summary_versions_are_immutable_while_cursor_advances(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = ConversationStore(str(path))
    history = [{"role": "user", "content": "Decidimos usar SQLite para Atlas."}]
    store.put("c", history, "alice", "Atlas")
    original = _checkpoints(store._db)
    assert len(original) == 1
    assert json.loads(original[0][1])["processed_count"] == 1

    for i in range(12):
        history.extend([
            {"role": "assistant", "content": "Entendido."},
            {"role": "user", "content": f"Charla común {i}."},
        ])
        store.put("c", history, "alice", "Atlas")
    assert _checkpoints(store._db) == original
    assert store.get_summary("c", "alice")["processed_count"] == len(history)
    assert store.get_summary("c", "alice")["version"] == 1

    history.append({"role": "user", "content": "Corrijo: el respaldo será diario."})
    store.put("c", history, "alice", "Atlas")
    checkpoints = _checkpoints(store._db)
    assert len(checkpoints) == 2
    assert checkpoints[0] == original[0]
    assert json.loads(checkpoints[1][1])["processed_count"] == len(history)
    assert store.get_summary("c", "alice")["version"] == 2
    assert store.get_summary("c", "bob") is None
    store._db.close()


def test_state_survives_backup_and_legacy_checkpoint_without_state(tmp_path):
    path = tmp_path / "live.sqlite3"
    store = ConversationStore(str(path))
    history = [{"role": "user", "content": "Decidimos conservar el historial."}]
    store.put("c", history, "alice", "Atlas")
    first = _checkpoints(store._db)
    history.append({"role": "assistant", "content": "De acuerdo."})
    store.put("c", history, "alice", "Atlas")
    backup = tmp_path / "restored.sqlite3"
    with sqlite3.connect(backup) as destination:
        store._db.backup(destination)
    restored = ConversationStore(str(backup))
    assert restored.get_summary("c", "alice")["processed_count"] == 2
    assert _checkpoints(restored._db) == first

    # Simulate an upgraded installation whose old database has no state row.
    restored._db.execute(
        "DELETE FROM conversation_summary_state WHERE owner='alice' AND conversation_id='c'"
    )
    restored._db.commit()
    history.append({"role": "user", "content": "Falta probar la restauración."})
    restored.put("c", history, "alice", "Atlas")
    assert restored.get_summary("c", "alice")["processed_count"] == 3
    assert restored.get_summary("c", "alice")["version"] == 2
    assert _checkpoints(restored._db)[0] == first[0]
    store._db.close()
    restored._db.close()


def test_failed_cursor_write_rolls_back_history_and_checkpoint(tmp_path):
    path = tmp_path / "rollback.sqlite3"
    store = ConversationStore(str(path))
    history = [{"role": "user", "content": "Decidimos usar SQLite para Atlas."}]
    store.put("c", history, "alice", "Atlas")
    baseline = store.get_summary("c", "alice")
    checkpoints = _checkpoints(store._db)
    store._db.execute(
        "CREATE TRIGGER deny_state_update BEFORE UPDATE ON conversation_summary_state "
        "BEGIN SELECT RAISE(ABORT, 'simulated_state_failure'); END"
    )
    store._db.commit()
    with pytest.raises(sqlite3.IntegrityError, match="simulated_state_failure"):
        store.put("c", history + [
            {"role": "user", "content": "Corrijo: usaremos PostgreSQL."}
        ], "alice", "Atlas")

    reopened = ConversationStore(str(path))
    assert reopened.get("c", "alice") == history
    assert reopened.get_summary("c", "alice") == baseline
    assert _checkpoints(reopened._db) == checkpoints
    reopened._db.close()
    store._db.close()


def test_image_replay_cannot_mutate_existing_turn_or_checkpoint(tmp_path):
    store = ConversationStore(str(tmp_path / "images.sqlite3"))
    history = [{"role": "user", "content": "Decidimos adjuntar el plano."}]
    store.put("c", history, "alice", "Atlas",
              image_attachments=[("plano.png", "data:image/png;base64,AA==")])
    baseline = store.get_summary("c", "alice")
    with pytest.raises(ValueError, match="image_attachments_require_new_user_turn"):
        store.put("c", history, "alice", "Atlas",
                  image_attachments=[("duplicado.png", "data:image/png;base64,BB==")])
    assert len(store.images_for_conversation("c", "alice")) == 1
    assert store.get_summary("c", "alice") == baseline
    store._db.close()
