"""Durability regressions: atomic deletion, attachment ownership, read isolation."""
from __future__ import annotations

import sqlite3
from threading import Event, Thread

import pytest

from iachat.store import ConversationStore


def _seed(store: ConversationStore) -> None:
    store.put("atlas", [
        {"role": "user", "content": "Decidimos conservar los planos originales."},
        {"role": "assistant", "content": "Entendido."},
    ], "alice", "Atlas")
    store.save_images("atlas", "alice", 0, ["data:image/png;base64,AA=="], ["plano.png"])


def test_failed_attachment_cleanup_rolls_back_entire_conversation_delete(tmp_path):
    path = tmp_path / "memory.sqlite3"
    store = ConversationStore(str(path))
    _seed(store)
    original = store.get("atlas", "alice")
    summary = store.get_summary("atlas", "alice")
    store._db.execute(
        "CREATE TRIGGER deny_attachment_delete BEFORE DELETE ON image_attachments "
        "BEGIN SELECT RAISE(ABORT, 'simulated_cleanup_failure'); END"
    )
    store._db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="simulated_cleanup_failure"):
        store.delete("atlas", "alice")

    # A second connection sees the original committed transcript, metadata,
    # image and summary, not a half-deleted conversation.
    reopened = ConversationStore(str(path))
    assert reopened.get("atlas", "alice") == original
    assert reopened.get_summary("atlas", "alice") == summary
    assert len(reopened.images_for_conversation("atlas", "alice")) == 1
    assert reopened.list_conversations("alice")[0]["project"] == "Atlas"
    reopened._db.close()

    store._db.execute("DROP TRIGGER deny_attachment_delete")
    store._db.commit()
    assert store.delete("atlas", "alice")
    assert store.get("atlas", "alice") is None
    assert store.get_summary("atlas", "alice") is None
    assert store.images_for_conversation("atlas", "alice") == []
    store._db.close()


def test_legacy_image_writer_rejects_orphans_wrong_owner_and_assistant_turn(tmp_path):
    store = ConversationStore(str(tmp_path / "images.sqlite3"))
    _seed(store)
    image = ["data:image/png;base64,AA=="]
    name = ["other.png"]
    for owner, index in (("bob", 0), ("alice", 1), ("alice", 99)):
        with pytest.raises(ValueError):
            store.save_images("atlas", owner, index, image, name)
    with pytest.raises(ValueError, match="image_attachment_count_mismatch"):
        store.save_images("atlas", "alice", 0, image, [])
    with pytest.raises(ValueError, match="invalid_image_message_index"):
        store.save_images("atlas", "alice", True, image, name)
    assert [i["filename"] for i in store.images_for_conversation("atlas", "alice")] == ["plano.png"]
    assert store.images_for_conversation("atlas", "bob") == []
    store._db.close()


def test_exists_waits_for_rollback_of_uncommitted_conversation(tmp_path):
    store = ConversationStore(str(tmp_path / "isolation.sqlite3"))
    written, release, finished = Event(), Event(), Event()
    result = []

    def writer():
        with store._lock, store._db:
            store._db.execute("BEGIN IMMEDIATE")
            store._db.execute(
                "INSERT INTO conversations(id,history,owner) VALUES(?,?,?)",
                ("pending", "[]", "alice"),
            )
            written.set()
            assert release.wait(5)
            store._db.rollback()

    def reader():
        result.append(store.exists("pending", "alice"))
        finished.set()

    writer_thread = Thread(target=writer)
    reader_thread = Thread(target=reader)
    writer_thread.start()
    assert written.wait(5)
    reader_thread.start()
    try:
        assert not finished.wait(0.1), "read exposed an uncommitted conversation"
    finally:
        release.set()
        writer_thread.join(5)
        reader_thread.join(5)
    assert finished.is_set()
    assert result == [False]
    store._db.close()
