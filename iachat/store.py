from __future__ import annotations
import json
import sqlite3
import time
import hashlib
import secrets
from threading import Lock

class ConversationStore:
    def __init__(self, path: str = "iachat.db") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, history TEXT NOT NULL)"
        )
        self._db.execute("CREATE TABLE IF NOT EXISTS conversation_index (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS memories (id TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at INTEGER NOT NULL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, admin INTEGER NOT NULL DEFAULT 0)")
        for table in ("conversations", "conversation_index", "memories"):
            cols = {c[1] for c in self._db.execute(f"PRAGMA table_info({table})")}
            if "owner" not in cols:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN owner TEXT NOT NULL DEFAULT 'admin'")
        self._db.commit()
        self._lock = Lock()

    @staticmethod
    def _digest(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260000).hex()

    def create_user(self, username: str, password: str, admin: bool = False) -> bool:
        salt = secrets.token_hex(16)
        encoded = salt + ":" + self._digest(password, salt)
        with self._lock:
            try:
                self._db.execute("INSERT INTO users(username,password_hash,admin) VALUES(?,?,?)", (username, encoded, int(admin)))
                self._db.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def verify_user(self, username: str, password: str) -> bool:
        row = self._db.execute("SELECT password_hash FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
        if row is None:
            return False
        salt, expected = row[0].split(":", 1)
        return secrets.compare_digest(self._digest(password, salt), expected)

    def get_user(self, username: str) -> dict | None:
        row = self._db.execute("SELECT username, enabled, admin FROM users WHERE username=?", (username,)).fetchone()
        return {"username": row[0], "enabled": bool(row[1]), "admin": bool(row[2])} if row else None

    def list_users(self) -> list[dict]:
        rows = self._db.execute("SELECT username,enabled,admin FROM users ORDER BY username").fetchall()
        return [{"username": r[0], "enabled": bool(r[1]), "admin": bool(r[2])} for r in rows]

    def set_enabled(self, username: str, enabled: bool) -> bool:
        with self._lock:
            cursor = self._db.execute("UPDATE users SET enabled=? WHERE username=? AND admin=0", (int(enabled), username))
            self._db.commit()
            return cursor.rowcount > 0

    def change_password(self, username: str, password: str) -> None:
        salt = secrets.token_hex(16)
        with self._lock:
            self._db.execute("UPDATE users SET password_hash=? WHERE username=?", (salt + ":" + self._digest(password, salt), username))
            self._db.commit()

    def exists(self, conversation_id: str, owner: str = "admin") -> bool:
        row = self._db.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?", (conversation_id, owner)).fetchone()
        return row is not None

    def get(self, conversation_id: str, owner: str = "admin") -> list[dict[str, str]] | None:
        row = self._db.execute("SELECT history FROM conversations WHERE id=? AND owner=?", (conversation_id, owner)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return [{"role": str(item["role"]), "content": str(item["content"])} for item in data]

    def list_conversations(self, owner: str = "admin") -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT c.id, COALESCE(i.title, 'Conversación'), COALESCE(i.updated_at, 0) "
                "FROM conversations c LEFT JOIN conversation_index i ON i.id=c.id "
                "WHERE c.owner=? ORDER BY COALESCE(i.updated_at, 0) DESC, c.rowid DESC", (owner,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]

    def put(self, conversation_id: str, history: list[dict[str, str]], owner: str = "admin") -> None:
        payload = json.dumps(history, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations(id, history, owner) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET history=excluded.history WHERE conversations.owner=excluded.owner",
                (conversation_id, payload, owner),
            )
            title = next((m["content"][:80] for m in history if m.get("role") == "user"), "Conversación")
            self._db.execute(
                "INSERT INTO conversation_index(id, title, updated_at, owner) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at WHERE conversation_index.owner=excluded.owner",
                (conversation_id, title, int(time.time()), owner),
            )
            self._db.commit()

    def delete(self, conversation_id: str, owner: str = "admin") -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM conversations WHERE id=? AND owner=?", (conversation_id, owner))
            self._db.execute("DELETE FROM conversation_index WHERE id=? AND owner=?", (conversation_id, owner))
            self._db.commit()
        return cursor.rowcount > 0

    def list_memories(self, owner: str = "admin") -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, content, updated_at FROM memories WHERE owner=? ORDER BY updated_at DESC, id", (owner,)).fetchall()
        return [{"id": row[0], "content": row[1], "updated_at": row[2]} for row in rows]

    def save_memory(self, memory_id: str, content: str, owner: str = "admin") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (id, content, updated_at, owner) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at WHERE memories.owner=excluded.owner",
                (memory_id, content, int(time.time()), owner),
            )
            self._db.commit()

    def delete_memory(self, memory_id: str, owner: str = "admin") -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM memories WHERE id=? AND owner=?", (memory_id, owner))
            self._db.commit()
            return cursor.rowcount > 0
