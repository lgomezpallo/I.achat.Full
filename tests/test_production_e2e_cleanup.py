"""The production E2E smoke must leave no orphaned private memory rows."""
import sqlite3
import runpy
from pathlib import Path

from iachat.store import ConversationStore

# The production launcher is an executable script, not an installed package.
# Load its real cleanup function without requiring scripts/ on PYTHONPATH.
cleanup_account = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "iachat_production_e2e.py")
)["cleanup_account"]


def test_temporary_e2e_account_cleanup_includes_summary_versions(tmp_path):
    path = str(tmp_path / "production-smoke.db")
    store = ConversationStore(path)
    assert store.create_user("e2e-temporary", "temporary-password")
    assert store.create_user("other-user", "other-password")
    history = [
        {"role": "user", "content": "Decidimos conservar el historial de prueba."},
        {"role": "assistant", "content": "Confirmado."},
    ]
    store.put("temporary-conversation", history, "e2e-temporary", "Test")
    store.put("other-conversation", history, "other-user", "Test")
    assert store.get_summary("temporary-conversation", "e2e-temporary") is not None

    cleanup_account(path, "e2e-temporary")

    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM users WHERE username='e2e-temporary'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM conversations WHERE owner='e2e-temporary'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM conversation_summary_versions WHERE owner='e2e-temporary'").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM conversation_summary_versions WHERE owner='other-user'").fetchone()[0] == 1
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
