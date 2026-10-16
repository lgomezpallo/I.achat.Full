"""Owner-scoped SQLite persistence for Central conversation state.

Independent from IAchat's existing schema until integration is validated.
"""
import json
import sqlite3
from threading import Lock

from iachat.central_state import ConversationState, state_from_dict, state_to_dict


class CentralStateStore:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = Lock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS central_states ("
            "owner TEXT NOT NULL, conversation_id TEXT NOT NULL, "
            "payload TEXT NOT NULL, PRIMARY KEY(owner, conversation_id))"
        )
        self._db.commit()

    def load(self, owner: str, conversation_id: str) -> ConversationState | None:
        self._validate_identity(owner, conversation_id)
        with self._lock:
            row = self._db.execute(
                "SELECT payload FROM central_states WHERE owner=? AND conversation_id=?",
                (owner, conversation_id),
            ).fetchone()
        return state_from_dict(json.loads(row[0])) if row else None

    def save(self, owner: str, conversation_id: str, state: ConversationState) -> None:
        self._validate_identity(owner, conversation_id)
        payload = json.dumps(state_to_dict(state), ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT INTO central_states(owner,conversation_id,payload) VALUES(?,?,?) "
                "ON CONFLICT(owner,conversation_id) DO UPDATE SET payload=excluded.payload",
                (owner, conversation_id, payload),
            )
            self._db.commit()

    def delete(self, owner: str, conversation_id: str) -> bool:
        self._validate_identity(owner, conversation_id)
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM central_states WHERE owner=? AND conversation_id=?",
                (owner, conversation_id),
            )
            self._db.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @staticmethod
    def _validate_identity(owner: str, conversation_id: str) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("owner is required")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id is required")
