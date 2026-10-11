"""Bounded conversational context for Router without altering stored transcripts.

Long histories remain complete in SQLite. Only the last turns that fit a
conservative character budget are sent to the model. This is not a summary:
older omitted turns must never be represented as remembered facts.
"""
from __future__ import annotations

MAX_HISTORY_CHARS = 32000


def recent_context(history: list[dict[str, str]], budget: int = MAX_HISTORY_CHARS) -> list[dict[str, str]]:
    """Keep recent complete chat turns, preserving chronological order."""
    if budget <= 0:
        return []
    selected: list[dict[str, str]] = []
    used = 0
    for entry in reversed(history):
        if entry.get("role") not in ("user", "assistant"):
            continue
        content = entry.get("content", "")
        if not isinstance(content, str) or not content:
            continue
        size = len(content)
        if size > budget - used:
            break
        selected.append({"role": entry["role"], "content": content})
        used += size
    selected.reverse()
    # Never begin with an orphan assistant response.
    while selected and selected[0]["role"] != "user":
        selected.pop(0)
    return selected
