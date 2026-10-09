from __future__ import annotations
import json
import sqlite3
import time
from threading import Lock

class ConversationStore:
    def __init__(self, path: str = "iachat.db") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, history TEXT NOT NULL)"
        )
        self._db.execute("CREATE TABLE IF NOT EXISTS conversation_index (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        self._db.commit()
        self._lock = Lock()

    def exists(self, conversation_id: str) -> bool:
        row = self._db.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        return row is not None

    def get(self, conversation_id: str) -> list[dict[str, str]] | None:
        row = self._db.execute("SELECT history FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return [{"role": str(item["role"]), "content": str(item["content"])} for item in data]

    def list_conversations(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT c.id, COALESCE(i.title, 'Conversación'), COALESCE(i.updated_at, 0) "
                "FROM conversations c LEFT JOIN conversation_index i ON i.id=c.id "
                "ORDER BY COALESCE(i.updated_at, 0) DESC, c.rowid DESC"
            ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]

    def put(self, conversation_id: str, history: list[dict[str, str]]) -> None:
        payload = json.dumps(history, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations(id, history) VALUES(?, ?) "
                "ON CONFLICT(id) DO UPDATE SET history=excluded.history",
                (conversation_id, payload),
            )
            title = next((m["content"][:80] for m in history if m.get("role") == "user"), "Conversación")
            self._db.execute(
                "INSERT INTO conversation_index(id, title, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
                (conversation_id, title, int(time.time())),
            )
            self._db.commit()

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
            self._db.execute("DELETE FROM conversation_index WHERE id=?", (conversation_id,))
            self._db.commit()
        return cursor.rowcount > 0

    def list_memories(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, content, updated_at FROM memories ORDER BY updated_at DESC, id").fetchall()
        return [{"id": row[0], "content": row[1], "updated_at": row[2]} for row in rows]

    def save_memory(self, memory_id: str, content: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (id, content, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at",
                (memory_id, content, int(time.time())),
            )
            self._db.commit()

    def delete_memory(self, memory_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            self._db.commit()
            return cursor.rowcount > 0
