"""Live free-provider memory acceptance probe for IAchat production E2E.

Only synthetic, isolated user turns are inserted. The provider is called once
through authenticated HTTP by the existing production E2E launcher. Never log
the synthetic answer, credentials, stored conversations or generated markers.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets

from iachat.conversation_summary import render_archived_evidence


def _memory_json(answer: str) -> dict | None:
    """Accept only a complete structured answer, not a negated or quoted claim.

    Loose substring checks can incorrectly pass 'no elegimos PostgreSQL' or
    'no recuerdo si era diario'. A real-provider acceptance gate must fail
    closed when the model does not provide affirmative, exact evidence.
    """
    if not isinstance(answer, str) or len(answer) > 2048:
        return None
    value = answer.strip()
    if value.startswith(chr(96) * 3) and value.endswith(chr(96) * 3):
        value = re.sub(r"^\x60{3}(?:json)?\s*\n?", "", value, flags=re.I)
        value = re.sub(r"\s*\x60{3}$", "", value)
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _literal(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def recall_flags(answer: str, marker: str) -> tuple[bool, bool, bool]:
    """Require exact affirmative JSON fields; never accept substring echoes."""
    data = _memory_json(answer)
    if data is None:
        return (False, False, False)
    return (
        _literal(data.get("base_de_datos")) == "postgresql",
        _literal(data.get("motor_violeta")) == marker.casefold(),
        _literal(data.get("respaldo")) == "diario",
    )


def recall_marker(answer: str, marker: str) -> bool:
    """Second inference must independently return the exact archived code."""
    data = _memory_json(answer)
    return data is not None and _literal(data.get("motor_violeta")) == marker.casefold()


def transcript_digest(history: list[dict], prefix_count: int = 480) -> str | None:
    """Hash every original message and metadata field, not just three anchors."""
    if len(history) < prefix_count:
        return None
    payload = json.dumps(history[:prefix_count], sort_keys=True,
                         ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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
    original_digest = transcript_digest(store.get(conversation_id, owner))
    prompt = (
        "Según lo que decidimos en ESTA conversación del proyecto Atlas: "
        "¿qué base de datos elegimos, qué código de motor tiene el componente "
        "Violeta y con qué frecuencia será el respaldo? "
        'Respondé SOLO un objeto JSON sin Markdown con claves "base_de_datos", '
        '"motor_violeta" y "respaldo"; usá valores literales exactos o null '
        'si no recordás algún dato. No agregues explicaciones.'
    )
    response = post_chat(client, "/api/chat", json={
        "conversation_id": conversation_id, "project": "Atlas", "text": prompt,
    })
    data = response.json() if response.status_code == 200 else {}
    answer = data.get("answer", "")
    flags = recall_flags(answer, marker)
    recall = response.status_code == 200 and all(flags)
    loaded = client.get("/api/conversations/" + conversation_id)
    history = loaded.json().get("history", []) if loaded.status_code == 200 else []
    durable = (
        len(history) == 482
        and original_digest is not None
        and transcript_digest(history) == original_digest
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
        "begin=" + str(flags[0]),
        "middle=" + str(flags[1]),
        "end=" + str(flags[2]),
        "history=" + str(len(history)),
        "owner_isolation=" + str(store.get(conversation_id, other_owner) is None),
        flush=True,
    )
    return bool(recall and durable)
