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
        self._db.execute("CREATE TABLE IF NOT EXISTS oidc_identities (provider TEXT NOT NULL, subject TEXT NOT NULL, username TEXT NOT NULL UNIQUE, PRIMARY KEY(provider,subject), FOREIGN KEY(username) REFERENCES users(username))")
        for table in ("conversations", "conversation_index", "memories"):
            cols = {c[1] for c in self._db.execute(f"PRAGMA table_info({table})")}
            if "owner" not in cols:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN owner TEXT NOT NULL DEFAULT 'admin'")
        # Nullable project column: existing memories stay general.
        memory_cols = {c[1] for c in self._db.execute("PRAGMA table_info(memories)")}
        if "project" not in memory_cols:
            self._db.execute("ALTER TABLE memories ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        index_cols = {c[1] for c in self._db.execute("PRAGMA table_info(conversation_index)")}
        if "project" not in index_cols:
            self._db.execute("ALTER TABLE conversation_index ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS automatic_memory_log ("
            "id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, owner TEXT NOT NULL, "
            "project TEXT NOT NULL, content TEXT NOT NULL, created_at INTEGER NOT NULL, "
            "undone INTEGER NOT NULL DEFAULT 0)"
        )
        event_cols = {c[1] for c in self._db.execute("PRAGMA table_info(automatic_memory_log)")}
        if "previous_content" not in event_cols:
            self._db.execute("ALTER TABLE automatic_memory_log ADD COLUMN previous_content TEXT")
        self._db.execute("CREATE TABLE IF NOT EXISTS image_attachments (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, owner TEXT NOT NULL, message_index INTEGER NOT NULL, filename TEXT NOT NULL, data_url TEXT NOT NULL)")
        self._db.execute("CREATE INDEX IF NOT EXISTS image_attachments_lookup ON image_attachments(conversation_id, owner, message_index)")
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

    def get_or_create_oidc_user(self, provider: str, subject: str) -> str:
        """Persist the verified provider subject; never link accounts by email."""
        if provider != "google" or not isinstance(subject, str) or not 1 <= len(subject) <= 255:
            raise ValueError("invalid_identity")
        with self._lock:
            row = self._db.execute(
                "SELECT u.username,u.enabled FROM oidc_identities i JOIN users u "
                "ON u.username=i.username WHERE i.provider=? AND i.subject=?",
                (provider, subject),
            ).fetchone()
            if row:
                if not row[1]:
                    raise ValueError("account_disabled")
                return row[0]
            username = "g_" + secrets.token_hex(12)
            salt = secrets.token_hex(16)
            # OIDC users have an unknown random password and cannot log in by password.
            password_hash = salt + ":" + self._digest(secrets.token_urlsafe(48), salt)
            try:
                self._db.execute(
                    "INSERT INTO users(username,password_hash,enabled,admin) VALUES(?,?,1,0)",
                    (username, password_hash),
                )
                self._db.execute(
                    "INSERT INTO oidc_identities(provider,subject,username) VALUES(?,?,?)",
                    (provider, subject, username),
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
            return username

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

    def images_for_conversation(self, conversation_id: str, owner: str = "admin") -> list[dict]:
        rows = self._db.execute("SELECT message_index, filename, data_url FROM image_attachments WHERE conversation_id=? AND owner=? ORDER BY message_index,id", (conversation_id, owner)).fetchall()
        return [{"message_index": r[0], "filename": r[1], "data_url": r[2]} for r in rows]

    def save_images(self, conversation_id: str, owner: str, message_index: int, images: list[str], names: list[str]) -> None:
        with self._lock:
            self._db.executemany("INSERT INTO image_attachments(conversation_id,owner,message_index,filename,data_url) VALUES(?,?,?,?,?)", [(conversation_id,owner,message_index,name,image) for name,image in zip(names,images)])
            self._db.commit()

    def list_conversations(self, owner: str = "admin", project: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT c.id, COALESCE(i.title, 'Conversación'), COALESCE(i.updated_at, 0), COALESCE(i.project, '') "
                "FROM conversations c LEFT JOIN conversation_index i ON i.id=c.id "
                "WHERE c.owner=? ORDER BY COALESCE(i.updated_at, 0) DESC, c.rowid DESC", (owner,)
            ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2], "project": r[3]} for r in rows if project is None or r[3] == project]

    def put(self, conversation_id: str, history: list[dict[str, str]], owner: str = "admin", project: str = "") -> None:
        payload = json.dumps(history, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO conversations(id, history, owner) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET history=excluded.history WHERE conversations.owner=excluded.owner",
                (conversation_id, payload, owner),
            )
            title = next((m["content"][:80] for m in history if m.get("role") == "user"), "Conversación")
            self._db.execute(
                "INSERT INTO conversation_index(id, title, updated_at, owner, project) VALUES(?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at WHERE conversation_index.owner=excluded.owner",
                (conversation_id, title, int(time.time()), owner, project),
            )
            self._db.commit()

    def conversation_project(self, conversation_id: str, owner: str = "admin") -> str | None:
        row = self._db.execute(
            "SELECT i.project FROM conversation_index i JOIN conversations c ON c.id=i.id "
            "WHERE i.id=? AND c.owner=? AND i.owner=?", (conversation_id, owner, owner)
        ).fetchone()
        return row[0] if row else None

    def move_conversation(self, conversation_id: str, project: str, owner: str = "admin") -> bool:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE conversation_index SET project=? WHERE id=? AND owner=? "
                "AND EXISTS(SELECT 1 FROM conversations WHERE id=? AND owner=?)",
                (project, conversation_id, owner, conversation_id, owner))
            self._db.commit()
            return cursor.rowcount > 0

    def delete(self, conversation_id: str, owner: str = "admin") -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM conversations WHERE id=? AND owner=?", (conversation_id, owner))
            self._db.execute("DELETE FROM conversation_index WHERE id=? AND owner=?", (conversation_id, owner))
            self._db.execute("DELETE FROM image_attachments WHERE conversation_id=? AND owner=?", (conversation_id, owner))
            self._db.commit()
        return cursor.rowcount > 0

    def search_conversations(self, query: str, owner: str = "admin", limit: int = 25, project: str | None = None) -> list[dict]:
        """Owner-scoped literal text search; never sends conversation content to a model."""
        needle = query.strip().casefold()
        if len(needle) < 2:
            return []
        matches = []
        for info in self.list_conversations(owner, project):
            history = self.get(info["id"], owner) or []
            found = next((m["content"] for m in history
                          if needle in m.get("content", "").casefold()), None)
            if found is None and needle not in info["title"].casefold():
                continue
            excerpt = found or info["title"]
            pos = excerpt.casefold().find(needle)
            start = max(0, pos - 70)
            snippet = excerpt[start:start + 210]
            matches.append({**info, "excerpt": snippet})
            if len(matches) >= limit:
                break
        return matches

    def list_memories(self, owner: str = "admin", project: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT id, content, updated_at, project FROM memories WHERE owner=? ORDER BY updated_at DESC, id", (owner,)).fetchall()
        return [{"id": row[0], "content": row[1], "updated_at": row[2], "project": row[3]} for row in rows if project is None or row[3] == "" or row[3] == project]

    def save_memory(self, memory_id: str, content: str, owner: str = "admin", project: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO memories (id, content, updated_at, owner, project) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at, project=excluded.project WHERE memories.owner=excluded.owner",
                (memory_id, content, int(time.time()), owner, project),
            )
            self._db.commit()

    def save_automatic_memory(self, memory_id: str, content: str, owner: str = "admin", project: str = "") -> None:
        """Atomically save a new automatically learned memory and its audit entry."""
        with self._lock:
            self._db.execute(
                "INSERT INTO memories(id,content,updated_at,owner,project) VALUES(?,?,?,?,?)",
                (memory_id, content, int(time.time()), owner, project))
            self._db.execute(
                "INSERT INTO automatic_memory_log(id,memory_id,owner,project,content,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (memory_id, memory_id, owner, project, content, int(time.time())))
            self._db.commit()

    def replace_automatic_memory(self, memory_id: str, old: str, new: str, owner: str, project: str) -> bool:
        """Compare-and-swap an automatic memory, preserving a reversible event."""
        with self._lock:
            row = self._db.execute(
                "SELECT content,project FROM memories WHERE id=? AND owner=?",
                (memory_id, owner)).fetchone()
            if not row or row[0] != old or row[1] != project:
                return False
            # Never overwrite user-edited entries: require a matching original auto-save.
            origin = self._db.execute(
                "SELECT 1 FROM automatic_memory_log WHERE memory_id=? AND owner=? "
                "AND previous_content IS NULL AND content=? LIMIT 1",
                (memory_id, owner, old)).fetchone()
            if not origin:
                return False
            self._db.execute(
                "UPDATE memories SET content=?,updated_at=? WHERE id=? AND owner=? AND project=?",
                (new, int(time.time()), memory_id, owner, project))
            self._db.execute(
                "INSERT INTO automatic_memory_log(id,memory_id,owner,project,content,created_at,previous_content) "
                "VALUES(?,?,?,?,?,?,?)",
                (secrets.token_hex(16), memory_id, owner, project, new, int(time.time()), old))
            self._db.commit()
            return True

    def list_automatic_memory_log(self, owner: str = "admin", limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, memory_id, project, content, created_at, undone, previous_content "
                "FROM automatic_memory_log WHERE owner=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (owner, limit)).fetchall()
        return [{"id": row[0], "memory_id": row[1], "project": row[2],
                 "content": row[3], "created_at": row[4], "undone": bool(row[5]), "previous_content": row[6]} for row in rows]

    def undo_automatic_memory(self, event_id: str, owner: str = "admin") -> bool:
        """Undo only if the remembered text is unchanged; never delete a user's edit."""
        with self._lock:
            row = self._db.execute(
                "SELECT memory_id,content FROM automatic_memory_log "
                "WHERE id=? AND owner=? AND undone=0", (event_id, owner)).fetchone()
            if row is None:
                return False
            current = self._db.execute(
                "SELECT content,project FROM memories WHERE id=? AND owner=?", (row[0], owner)).fetchone()
            event = self._db.execute(
                "SELECT content,previous_content,project FROM automatic_memory_log WHERE id=? AND owner=?",
                (event_id, owner)).fetchone()
            if current is None or event is None or current != (event[0], event[2]):
                return False
            if event[1] is None:
                self._db.execute("DELETE FROM memories WHERE id=? AND owner=?", (row[0], owner))
            else:
                self._db.execute(
                    "UPDATE memories SET content=?,updated_at=? WHERE id=? AND owner=?",
                    (event[1], int(time.time()), row[0], owner))
            self._db.execute("UPDATE automatic_memory_log SET undone=1 WHERE id=? AND owner=?", (event_id, owner))
            self._db.commit()
            return True

    def delete_memory(self, memory_id: str, owner: str = "admin") -> bool:
        with self._lock:
            cursor = self._db.execute("DELETE FROM memories WHERE id=? AND owner=?", (memory_id, owner))
            self._db.commit()
            return cursor.rowcount > 0
