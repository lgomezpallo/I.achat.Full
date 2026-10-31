"""Regression: failed account creation must not poison durable chat writes.

SQLite keeps an implicit transaction open after a UNIQUE constraint failure.
ConversationStore.put starts BEGIN IMMEDIATE, so duplicate account creation
must explicitly roll back before later messages can be persisted.
"""
from iachat.store import ConversationStore


def test_duplicate_user_creation_does_not_break_durable_conversation(tmp_path):
    path = str(tmp_path / "durable.db")
    store = ConversationStore(path)
    assert store.create_user("alice", "first-password")
    assert not store.create_user("alice", "second-password")
    assert not store._db.in_transaction
    assert store.verify_user("alice", "first-password")
    assert not store.verify_user("alice", "second-password")

    store.put(
        "chat-1",
        [{"role": "user", "content": "Decidimos conservar el historial completo."}],
        "alice",
        "Atlas",
    )
    reopened = ConversationStore(path)
    assert reopened.get("chat-1", "alice") == [
        {"role": "user", "content": "Decidimos conservar el historial completo."}
    ]
    assert reopened.get_summary("chat-1", "alice")["processed_count"] == 1
    assert reopened.get("chat-1", "bob") is None


def test_duplicate_user_creation_does_not_break_followup_append(tmp_path):
    store = ConversationStore(str(tmp_path / "followup.db"))
    store.put("chat-2", [{"role": "user", "content": "Falta revisar el backup."}], "alice")
    assert store.create_user("alice", "original")
    assert not store.create_user("alice", "duplicate")
    store.put(
        "chat-2",
        [
            {"role": "user", "content": "Falta revisar el backup."},
            {"role": "assistant", "content": "Anotado."},
            {"role": "user", "content": "Decidimos probar la restauración."},
        ],
        "alice",
    )
    assert len(store.get("chat-2", "alice")) == 3
    assert store.get_summary("chat-2", "alice")["processed_count"] == 3
