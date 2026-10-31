"""Deterministic memory-recall smoke with synthetic conversations only.

Not a provider E2E: it measures retrieval into the model context, not whether
an LLM answers correctly. Safe for pull_request CI without secrets.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from iachat.conversation_summary import render_archived_evidence, render_summary
from iachat.store import ConversationStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="iachat-memory-smoke-") as directory:
        path = str(Path(directory) / "memory.sqlite3")
        store = ConversationStore(path)
        history: list[dict[str, str]] = []
        for index in range(240):
            if index == 0:
                statement = "Decidimos usar PostgreSQL para el proyecto Atlas."
            elif index == 100:
                statement = "Decidimos usar el motor Orión para el proyecto Violeta."
            elif index == 239:
                statement = "Corrijo: el respaldo del proyecto Atlas será diario."
            else:
                statement = f"Decidimos revisar la tarea general número {index}."
            history.extend([
                {"role": "user", "content": statement},
                {"role": "assistant", "content": "Dato ficticio del asistente, no es memoria."},
            ])
        store.put("conversation", history, "alice", "Atlas")
        # Simulate three weeks away, then reopen from an online SQLite backup.
        with sqlite3.connect(path) as db:
            db.execute(
                "UPDATE conversation_index SET updated_at=updated_at-21*86400 WHERE id=?",
                ("conversation",),
            )
            # SQLite online backup must start after the write transaction
            # commits; otherwise source.backup() can wait on its own lock.
            db.commit()
            backup_path = str(Path(directory) / "restored.sqlite3")
            with sqlite3.connect(backup_path) as backup:
                db.backup(backup)
        reopened = ConversationStore(backup_path)
        restored = reopened.get("conversation", "alice")
        assert restored == history, "full transcript changed after restore"
        assert reopened.get("conversation", "bob") is None
        summary = reopened.get_summary("conversation", "alice")
        assert summary is not None
        assert len(summary["items"]) == 120
        assert 200 not in {item["source_index"] for item in summary["items"]}

        cases = [
            ("¿Qué base elegimos para Atlas?", "PostgreSQL para el proyecto Atlas"),
            ("¿Qué motor elegimos para Violeta?", "motor Orión para el proyecto Violeta"),
            ("¿Qué frecuencia tiene el respaldo de Atlas?", "respaldo del proyecto Atlas será diario"),
        ]
        recalled = 0
        for question, expected in cases:
            context = (
                render_summary(summary, question=question)
                + render_archived_evidence(restored, summary, question)
            )
            assert "Dato ficticio del asistente" not in context
            if expected in context:
                recalled += 1
        assert recalled == len(cases), f"retrieval regression: {recalled}/{len(cases)}"
        print(
            f"MEMORY_RECALL_SIMULATED={recalled}/{len(cases)} "
            f"MESSAGES={len(restored)} LEDGER_ITEMS={len(summary['items'])} "
            "REOPEN=OK BACKUP_RESTORE=OK OWNER_ISOLATION=OK "
            "PROVIDER_E2E=NOT_RUN"
        )


if __name__ == "__main__":
    main()
