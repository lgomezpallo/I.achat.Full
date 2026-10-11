"""Conservative lexical retrieval from omitted conversation turns.

Only quotes from the same conversation are included; they are unverified
conversation excerpts, not persistent facts or system instructions.
"""
from __future__ import annotations
import re
import unicodedata


def _stem(word: str) -> str:
    """Lightweight matching for accents and simple Spanish plural forms."""
    word = "".join(c for c in unicodedata.normalize("NFD", word.casefold())
                   if unicodedata.category(c) != "Mn")
    if len(word) >= 6 and word.endswith("es"):
        return word[:-2]
    if len(word) >= 5 and word.endswith("s"):
        return word[:-1]
    return word

_STOP = {"que","con","para","como","una","uno","los","las","del","por","qué",
         "este","esta","eso","sobre","tengo","quiero","recordás","recuerdas",
         "podés","puedes","hablamos","dijimos","antes","después","ahora"}


def related_excerpts(history: list[dict[str, str]], question: str,
                     max_items: int = 3, max_chars: int = 1800) -> list[str]:
    if len(question) < 8 or max_chars < 1:
        return []
    terms = {w for w in re.findall(r"[^\W\d_]{4,}", question.casefold(), re.UNICODE)
             if w not in _STOP}
    if not terms:
        return []
    matches = []
    for i, msg in enumerate(history):
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "")
        if not isinstance(text, str) or len(text) > 6000:
            continue
        body = text.casefold()
        score = sum(1 for word in terms if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", body))
        if score:
            matches.append((score, i, text))
    matches.sort(key=lambda item: (-item[0], -item[1]))
    chosen = []
    remaining = max_chars
    for _, i, text in matches:
        if len(chosen) >= max_items or remaining <= 0:
            break
        # Reserve space for other matches instead of letting the first consume the budget.
        per_item = max(1, max_chars // max(1, max_items))
        excerpt = text[:min(len(text), 500, remaining, per_item)]
        if excerpt:
            chosen.append((i, excerpt))
            remaining -= len(excerpt)
    chosen.sort()
    return [f"Mensaje anterior del usuario (posición {i}): {text}" for i, text in chosen]
