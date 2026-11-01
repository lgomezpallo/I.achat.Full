"""Backup/restore and migration checks for durable conversation memory."""
import json
import sqlite3

from iachat.store import ConversationStore


def test_sqlite_online_backup_restores_full_history_and_summary(tmp_path):
    live = str(tmp_path / "live.db")
    backup = str(tmp_path / "backup.db")
    store = ConversationStore(live)
    history = []
    for i in range(110):
        text = (
            "Decidimos guardar el historial completo." if i == 0
            else "Falta validar restauración de backup." if i == 55
            else "Corrijo: backup diario, no semanal." if i == 109
            else f"Turno de prueba {i}."
        )
        history.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": "Respuesta de prueba."},
        ])
    store.put("c", history, "alice", "Proyecto")
    with sqlite3.connect(live) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    restored = ConversationStore(backup)
    assert restored.get("c", "alice") == history
    summary = restored.get_summary("c", "alice")
    assert summary["processed_count"] == len(history)
    assert [x["source_index"] for x in summary["items"]] == [0, 110, 218]
    assert restored.get("c", "bob") is None
    assert restored.get_summary("c", "bob") is None
    with sqlite3.connect(backup) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_legacy_history_gets_first_summary_on_next_safe_append(tmp_path):
    path = str(tmp_path / "legacy.db")
    old_history = [
        {"role": "user", "content": "Decidimos conservar los mensajes."},
        {"role": "assistant", "content": "Entendido."},
    ]
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY, history TEXT NOT NULL)")
        db.execute("INSERT INTO conversations VALUES(?,?)", ("legacy", json.dumps(old_history)))
    store = ConversationStore(path)
    assert store.get_summary("legacy", "admin") is None
    store.put("legacy", [
        *old_history,
        {"role": "user", "content": "Falta revisar el backup."},
        {"role": "assistant", "content": "Pendiente."},
    ], "admin")
    summary = store.get_summary("legacy", "admin")
    assert summary["version"] == 1
    assert [x["source_index"] for x in summary["items"]] == [0, 2]
    assert len(store.get("legacy", "admin")) == 4
