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


def test_private_online_backup_restores_image_and_versioned_memory_audit(tmp_path):
    from pathlib import Path
    from runpy import run_path
    import stat

    backup_database = run_path(str(Path(__file__).resolve().parents[1] /
                                   "scripts" / "backup_iachat_db.py"))["backup_database"]
    live = tmp_path / "live.sqlite3"
    snapshot = tmp_path / "snapshot.sqlite3"
    store = ConversationStore(str(live))
    first = [{"role": "user", "content": "Decidimos usar PostgreSQL para Atlas."}]
    store.put("atlas", first, "alice", "Atlas",
              image_attachments=[("plano.png", "data:image/png;base64,AA==")])
    history = first + [
        {"role": "assistant", "content": "Entendido."},
        {"role": "user", "content": "Corrijo: el respaldo será diario."},
    ]
    store.put("atlas", history, "alice", "Atlas")
    store.save_automatic_memory("mem-atlas", "Respaldo diario", "alice", "Atlas")
    versions = store._db.execute(
        "SELECT version,summary_json FROM conversation_summary_versions "
        "WHERE owner='alice' AND conversation_id='atlas' ORDER BY version"
    ).fetchall()
    assert len(versions) == 2

    backup_database(live, snapshot)
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600
    restored = ConversationStore(str(snapshot))
    assert restored.get("atlas", "alice") == history
    assert restored.get_summary("atlas", "alice") == store.get_summary("atlas", "alice")
    assert restored.images_for_conversation("atlas", "alice") == [
        {"message_index": 0, "filename": "plano.png",
         "data_url": "data:image/png;base64,AA=="}
    ]
    assert restored.list_automatic_memory_log("alice")[0]["content"] == "Respaldo diario"
    assert restored._db.execute(
        "SELECT version,summary_json FROM conversation_summary_versions "
        "WHERE owner='alice' AND conversation_id='atlas' ORDER BY version"
    ).fetchall() == versions
    assert restored.get("atlas", "bob") is None
    assert restored.images_for_conversation("atlas", "bob") == []
    restored._db.close()
    store._db.close()


def test_legacy_images_cannot_be_readded_to_committed_turn(tmp_path):
    """An old client cannot duplicate a persisted attachment after reconnect."""
    path = tmp_path / "legacy-images.sqlite3"
    writer = ConversationStore(str(path))
    writer.put("atlas", [{"role": "user", "content": "Plano inicial."}], "alice", "Atlas")
    writer.save_images("atlas", "alice", 0, ["data:image/png;base64,AA=="], ["original.png"])
    writer._db.close()

    reopened = ConversationStore(str(path))
    with pytest.raises(ValueError, match="image_attachments_already_saved"):
        reopened.save_images(
            "atlas", "alice", 0, ["data:image/png;base64,BB=="], ["duplicate.png"]
        )
    assert [i["filename"] for i in reopened.images_for_conversation("atlas", "alice")] == [
        "original.png"
    ]
    assert reopened.get("atlas", "alice") == [
        {"role": "user", "content": "Plano inicial."}
    ]
    # A newly appended user turn is still allowed its own first attachment.
    reopened.put("atlas", [
        {"role": "user", "content": "Plano inicial."},
        {"role": "user", "content": "Segundo plano."},
    ], "alice", "Atlas")
    reopened.save_images("atlas", "alice", 1, ["data:image/png;base64,CC=="], ["second.png"])
    assert [i["filename"] for i in reopened.images_for_conversation("atlas", "alice")] == [
        "original.png", "second.png"
    ]
    reopened._db.close()


def test_two_sqlite_connections_cannot_attach_twice_to_same_turn(tmp_path):
    """BEGIN IMMEDIATE makes the duplicate check cross-process safe."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = tmp_path / "concurrent-images.sqlite3"
    setup = ConversationStore(str(path))
    setup.put("atlas", [{"role": "user", "content": "Un único plano."}], "alice", "Atlas")
    setup._db.close()
    barrier = Barrier(2)
    first = ConversationStore(str(path))
    second = ConversationStore(str(path))

    def attempt(store: ConversationStore, name: str) -> str:
        barrier.wait(timeout=5)
        try:
            store.save_images(
                "atlas", "alice", 0, ["data:image/png;base64,AA=="], [name]
            )
            return "saved"
        except ValueError as exc:
            return str(exc)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda args: attempt(*args),
                ((first, "first.png"), (second, "second.png")),
            ))
    finally:
        first._db.close()
        second._db.close()
    assert sorted(results) == ["image_attachments_already_saved", "saved"]
    check = ConversationStore(str(path))
    assert len(check.images_for_conversation("atlas", "alice")) == 1
    check._db.close()
