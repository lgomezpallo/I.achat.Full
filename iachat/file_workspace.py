"""Private bounded text-file workspace. No shell execution or arbitrary filesystem paths."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from uuid import uuid4

ALLOWED_EXTENSIONS = frozenset((".txt", ".md", ".csv", ".json", ".html", ".pdf", ".docx", ".xlsx"))
MAX_CONTENT_BYTES = 200_000
MAX_FILES_PER_USER = 50


class WorkspaceError(ValueError):
    pass


def validate_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[\w .()\-]{1,80}", name, re.UNICODE):
        raise WorkspaceError("invalid_filename")
    if name.startswith(".") or name.strip() != name or not any(name.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise WorkspaceError("invalid_filename")
    return name


def validate_content(content: str) -> str:
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise WorkspaceError("file_too_large")
    return content


def parse_generated_file(answer: str) -> tuple[str, str]:
    """LLM output is untrusted data; reject anything other than one JSON object."""
    if not isinstance(answer, str):
        raise WorkspaceError("invalid_file_response")
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", cleaned, re.IGNORECASE)
        if not match:
            raise WorkspaceError("invalid_file_response")
        cleaned = match.group(1)
    try:
        payload = json.loads(cleaned)
    except (ValueError, TypeError) as exc:
        raise WorkspaceError("invalid_file_response") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str) or not isinstance(payload.get("content"), str):
        raise WorkspaceError("invalid_file_response")
    return validate_name(payload["name"]), validate_content(payload["content"])


class FileWorkspace:
    def __init__(self, db_path: str):
        self._db = sqlite3.connect(db_path, check_same_thread=False, timeout=15)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS workspace_files ("
                "id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,"
                "content TEXT NOT NULL, updated_at INTEGER NOT NULL)"
            )
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_workspace_files_owner ON workspace_files(owner)")
            self._db.commit()

    def list(self, owner: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id,name,length(CAST(content AS BLOB)) AS bytes,updated_at "
                "FROM workspace_files WHERE owner=? ORDER BY updated_at DESC LIMIT 50", (owner,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, owner: str, file_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id,name,content,updated_at FROM workspace_files WHERE id=? AND owner=?",
                (file_id, owner),
            ).fetchone()
        return dict(row) if row else None

    def save(self, owner: str, name: str, content: str, file_id: str | None = None) -> dict:
        name = validate_name(name)
        content = validate_content(content)
        with self._lock:
            if file_id:
                cursor = self._db.execute(
                    "UPDATE workspace_files SET name=?,content=?,updated_at=? WHERE id=? AND owner=?",
                    (name, content, int(time.time()), file_id, owner),
                )
                if not cursor.rowcount:
                    raise WorkspaceError("file_not_found")
            else:
                count = self._db.execute(
                    "SELECT count(*) FROM workspace_files WHERE owner=?", (owner,)
                ).fetchone()[0]
                if count >= MAX_FILES_PER_USER:
                    raise WorkspaceError("file_limit_reached")
                file_id = str(uuid4())
                self._db.execute(
                    "INSERT INTO workspace_files(id,owner,name,content,updated_at) VALUES(?,?,?,?,?)",
                    (file_id, owner, name, content, int(time.time())),
                )
            self._db.commit()
        return {"id": file_id, "name": name, "bytes": len(content.encode("utf-8"))}

    def delete(self, owner: str, file_id: str) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM workspace_files WHERE id=? AND owner=?", (file_id, owner)
            )
            self._db.commit()
        return bool(cursor.rowcount)
