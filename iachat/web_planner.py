"""Deterministic, bounded first-stage planner for IAchat web lookup.

A search is a tool action, not a claim that facts have been verified.  This
planner intentionally makes no provider calls; it works with both backends.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from .web_search import needs_current_information

MAX_SEARCH_QUERY = 300

# An explicit request to search is valid even for timeless documentation.
EXPLICIT_SEARCH = re.compile(
    r"^\s*[¿¡]?\s*(?:busc[aá](?:me)?|buscar|investig[aá]|investigar)\b"
    r"|\b(?:consult[aá]|verific[aá]|comprob[aá]|busc[aá])\b.{0,45}"
    r"\b(?:internet|web|fuentes?|p[aá]ginas?)\b",
    re.IGNORECASE,
)

# Only a narrow set of referential questions inherit a recent need for
# freshness.  Do not browse for arbitrary messages following a news query.
REFERENTIAL_FOLLOWUP = re.compile(
    r"^\s*[¿¡]?\s*(?:y\s+)?(?:"
    r"a\s+qu[eé]\s+hora\b|"
    r"(?:qu[eé]|cu[aá]l)\s+(?:canal|horario|resultado|fecha|d[ií]a)\b|"
    r"d[oó]nde\b|"
    r"c[oó]mo\s+(?:sali[oó]|termin[oó]|qued[oó])\b|"
    r"qui[eé]n\s+(?:gan[oó]|juega|transmite)\b|"
    r"(?:el|la|los|las)\s+(?:canal|horario|resultado|transmisi[oó]n|"
    r"formaci[oó]n|fecha|partido)\b|"
    r"qu[eé]\s+pas[oó]\s+(?:al\s+final|despu[eé]s)\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WebLookupPlan:
    action: Literal["answer", "search"]
    query: str = ""
    reason: str = ""


def plan_web_lookup(
    message: str,
    history: Sequence[Mapping[str, str]] = (),
    *,
    has_attachments: bool = False,
) -> WebLookupPlan:
    """Decide whether to fetch evidence without browsing or model inference.

    For now, attached files do not trigger web access; they may contain
    untrusted instructions and require a separate tool policy.
    """
    question = message.strip()
    if not question or has_attachments:
        return WebLookupPlan("answer", reason="empty_or_attachment")
    if needs_current_information(question):
        return WebLookupPlan("search", question[:MAX_SEARCH_QUERY], "current_question")
    if EXPLICIT_SEARCH.search(question):
        return WebLookupPlan("search", question[:MAX_SEARCH_QUERY], "explicit_search")
    if not REFERENTIAL_FOLLOWUP.match(question) or len(question) > 180:
        return WebLookupPlan("answer", reason="no_web_signal")

    # Restrict context to recent turns in the SAME conversation. Assistant
    # messages never count as a source of user search intent.
    users = [
        turn.get("content", "").strip()
        for turn in history[-8:]
        if turn.get("role") == "user" and isinstance(turn.get("content"), str)
    ]
    if not users:
        return WebLookupPlan("answer", reason="no_recent_context")
    context = ""
    if needs_current_information(users[-1]) or EXPLICIT_SEARCH.search(users[-1]):
        context = users[-1]
    elif (
        len(users) >= 2
        and REFERENTIAL_FOLLOWUP.match(users[-1])
        and (needs_current_information(users[-2]) or EXPLICIT_SEARCH.search(users[-2]))
    ):
        context = users[-2]
    if not context:
        return WebLookupPlan("answer", reason="unrelated_followup")
    query = f"{context} {question}"[:MAX_SEARCH_QUERY]
    return WebLookupPlan("search", query, "contextual_followup")
