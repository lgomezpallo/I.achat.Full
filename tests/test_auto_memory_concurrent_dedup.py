"""Cross-process SQLite transaction protects automatic-memory deduplication."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from iachat.auto_memory import learn
from iachat.store import ConversationStore


def test_simultaneous_preference_learning_has_one_memory_and_audit(tmp_path):
    path = str(tmp_path / "concurrent-preferences.sqlite3")
    left = ConversationStore(path)
    right = ConversationStore(path)
    barrier = Barrier(2)

    # Force both requests to observe the old empty state before either
    # reaches the transaction. The second, locked check must reject one.
    for store in (left, right):
        original = store.list_memories

        def stale_read(owner="admin", project=None, _original=original):
            rows = _original(owner, project)
            barrier.wait(timeout=8)
            return rows

        store.list_memories = stale_read

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(learn, left, "alice", "Prefiero respuestas breves.", "IAchat")
        second = pool.submit(learn, right, "alice", "prefiero   respuestas breves!", "IAchat")
        assert sorted([first.result(timeout=12), second.result(timeout=12)]) == [False, True]

    verified = ConversationStore(path)
    assert len(verified.list_memories("alice", "IAchat")) == 1
    assert len(verified.list_automatic_memory_log("alice")) == 1
    assert verified.list_memories("bob") == []


def test_atomic_insert_respects_existing_general_memory(tmp_path):
    store = ConversationStore(str(tmp_path / "general.sqlite3"))
    store.save_memory("manual", "Prefiero respuestas breves.", "alice", "")
    assert not store.save_automatic_memory(
        "automatic", "prefiero   respuestas breves!", "alice", "IAchat"
    )
    assert len(store.list_memories("alice")) == 1
    assert store.list_automatic_memory_log("alice") == []
    # Another owner and an unrelated preference are independent.
    assert store.save_automatic_memory(
        "bob-pref", "Prefiero respuestas breves.", "bob", "IAchat"
    )
    assert store.save_automatic_memory(
        "other-pref", "Prefiero respuestas detalladas.", "alice", "IAchat"
    )
    assert len(store.list_automatic_memory_log("alice")) == 1
