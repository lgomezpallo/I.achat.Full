"""Concurrent readers must not see a shared SQLite connection's uncommitted writes.

This exercises the same ConversationStore instance used by parallel HTTP requests.
"""
import json
from threading import Event, Thread

import pytest

from iachat.store import ConversationStore


@pytest.mark.parametrize("field", ["transcript", "image", "project"])
def test_reads_wait_for_transaction_and_return_only_committed_state(tmp_path, field):
    store = ConversationStore(str(tmp_path / "memory.sqlite3"))
    original = [
        {"role": "user", "content": "Decidimos usar PostgreSQL."},
        {"role": "assistant", "content": "Registrado."},
    ]
    store.put("c", original, "alice", "Atlas")
    store.save_images("c", "alice", 0, ["data:image/png;base64,AA=="], ["a.png"])

    def read():
        if field == "transcript":
            return store.get("c", "alice")
        if field == "image":
            return store.images_for_conversation("c", "alice")
        return store.conversation_project("c", "alice")

    expected = read()
    started, finished = Event(), Event()
    result = []
    errors = []

    def worker():
        started.set()
        try:
            result.append(read())
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = Thread(target=worker, daemon=True)
    try:
        with store._lock:
            store._db.execute("BEGIN IMMEDIATE")
            if field == "transcript":
                store._db.execute(
                    "UPDATE conversations SET history=? WHERE id='c'",
                    (json.dumps([{"role": "user", "content": "UNCOMMITTED"}]),),
                )
            elif field == "image":
                store._db.execute(
                    "UPDATE image_attachments SET data_url='UNCOMMITTED' WHERE conversation_id='c'"
                )
            else:
                store._db.execute(
                    "UPDATE conversation_index SET project='UNCOMMITTED' WHERE id='c'"
                )
            thread.start()
            assert started.wait(2)
            assert not finished.wait(0.15), "reader observed a transaction before commit"
            store._db.rollback()
        assert finished.wait(3)
        assert not errors
        assert result == [expected]
        assert store.get("c", "bob") is None
    finally:
        if store._db.in_transaction:
            store._db.rollback()
        thread.join(timeout=3)
        store._db.close()
