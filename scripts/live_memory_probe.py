"""Live free-provider memory acceptance probe for IAchat production E2E.

Only synthetic, isolated user turns are inserted. The provider is called once
through authenticated HTTP by the existing production E2E launcher. Never log
the synthetic answer, credentials, stored conversations or generated markers.
"""
from __future__ import annotations

import re
import secrets

from iachat.conversation_summary import render_archived_evidence


def seed_memory_probe(store, owner: str, conversation_id: str, marker: str) -> None:
    """Create 480 messages with facts at the beginning, middle and end."""
    history = []
    for index in range(240):
        if index == 0:
            statement = "Decidimos usar PostgreSQL como base de datos del proyecto Atlas."
        elif index == 100:
            statement = f"Decidimos usar el motor {marker} para el componente Violeta del proyecto Atlas."
        elif index == 239:
            statement = "Corrijo: el respaldo del proyecto Atlas será diario."
        else:
            statement = f"Decidimos revisar la tarea general número {index}."
        history.extend((
            {"role": "user", "content": statement},
            {"role": "assistant", "content": "Respuesta ficticia sin datos nuevos."},
        ))
    store.put(conversation_id, history, owner, "Atlas")
    summary = store.get_summary(conversation_id, owner)
    if not summary or summary["processed_count"] != 480 or len(summary["items"]) != 120:
        raise AssertionError("memory_probe_summary_not_bounded")
    if any(marker in item["quote"] for item in summary["items"]):
        raise AssertionError("memory_probe_middle_not_evicted")
    archived = render_archived_evidence(
        history, summary, "¿Qué motor elegimos para Violeta del proyecto Atlas?"
    )
    if marker not in archived:
        raise AssertionError("memory_probe_archived_retrieval_failed")


def run_live_memory_probe(client, store, owner: str, other_owner: str, post_chat) -> bool:
    """Require an actual model answer grounded in three distant user turns.

    post_chat is the existing rate-limited HTTP helper; no direct model calls,
    paid-provider overrides or retries are introduced.
    """
    conversation_id = "e2e-memory-" + secrets.token_hex(8)
    marker = "LUCERO" + secrets.token_hex(4).upper()
    seed_memory_probe(store, owner, conversation_id, marker)
    prompt = (
        "Según lo que decidimos en ESTA conversación del proyecto Atlas: "
        "¿qué base de datos elegimos, qué código de motor tiene el componente "
        "Violeta y con qué frecuencia será el respaldo? "
        "Respondé los tres datos, sin inventar."
    )
    response = post_chat(client, "/api/chat", json={
        "conversation_id": conversation_id, "project": "Atlas", "text": prompt,
    })
    data = response.json() if response.status_code == 200 else {}
    answer = data.get("answer", "")
    normalized = re.sub(r"[^A-Z0-9]", "", answer.upper()) if isinstance(answer, str) else ""
    recall = (
        response.status_code == 200
        and "POSTGRESQL" in normalized
        and marker in normalized
        and "DIARIO" in normalized
    )
    loaded = client.get("/api/conversations/" + conversation_id)
    history = loaded.json().get("history", []) if loaded.status_code == 200 else []
    durable = (
        len(history) == 482
        and history[0]["content"].startswith("Decidimos usar PostgreSQL")
        and marker in history[200]["content"]
        and history[478]["content"].startswith("Corrijo:")
        and history[-1].get("role") == "assistant"
        and store.get(conversation_id, other_owner) is None
        and store.get_summary(conversation_id, owner)["processed_count"] == 482
    )
    print(
        "LIVE_MEMORY_480:",
        "PASS" if recall and durable else "FAIL",
        "http=" + str(response.status_code),
        "begin=" + str("POSTGRESQL" in normalized),
        "middle=" + str(marker in normalized),
        "end=" + str("DIARIO" in normalized),
        "history=" + str(len(history)),
        "owner_isolation=" + str(store.get(conversation_id, other_owner) is None),
        flush=True,
    )
    return bool(recall and durable)
