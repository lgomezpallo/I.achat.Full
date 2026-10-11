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


# Small transparent synonym map; this is not an embedding model.
# A hit must still point to literal text in the original conversation.
_CONCEPTS = (
    {"auto", "coche", "automovil", "vehiculo"},
    {"celular", "telefono", "movil", "smartphone"},
    {"trabajo", "laburo", "empleo"},
    {"pelicula", "film", "peli"},
    {"computadora", "ordenador", "pc"},
    {"dinero", "plata"},
)


def _concept(word: str) -> str:
    stem = _stem(word)
    for index, group in enumerate(_CONCEPTS):
        if stem in {_stem(item) for item in group}:
            return "concept:" + str(index)
    return stem


def related_excerpts(history: list[dict[str, str]], question: str,
                     max_items: int = 3, max_chars: int = 1800) -> list[str]:
    if len(question) < 8 or max_chars < 1:
        return []
    terms = {_concept(w) for w in re.findall(r"[^\W\d_]{4,}", question.casefold(), re.UNICODE)
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
        words = {_concept(w) for w in re.findall(r"[^\W\d_]{4,}", text.casefold(), re.UNICODE)}
        score = len(terms & words)
        # One generic shared word is too weak when the question names
        # several specific subjects. Prefer precision over invented recall.
        if len(terms) >= 3 and score < 2:
            continue
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
        limit = min(len(text), 500, remaining, per_item)
        # Anchor the excerpt around a relevant word, not just the beginning.
        tokens = list(re.finditer(r"[^\W\d_]{4,}", text, re.UNICODE))
        hits = [m.start() for m in tokens if _concept(m.group()) in terms]
        if hits and len(text) > limit:
            center = hits[0]
            start = max(0, min(center - limit // 3, len(text) - limit))
        else:
            start = 0
        excerpt = text[start:start + limit]
        if excerpt:
            chosen.append((i, excerpt))
            remaining -= len(excerpt)
    chosen.sort()
    return [f"Mensaje anterior del usuario (posición {i}): {text}" for i, text in chosen]
