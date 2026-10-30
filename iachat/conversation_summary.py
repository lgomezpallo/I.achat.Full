"""Versioned, extractive conversation ledger: only explicit user statements.

This is deliberately not a model-generated summary. Each entry is a quote with
a source message index. The full transcript remains authoritative in SQLite.
"""
from __future__ import annotations

import hashlib
import json
import re

_RULES = (
    ("cambio", re.compile(r"^(?:corrijo|correcci[oó]n\s*:|rectifico|en realidad\b|cambiamos\b|cambi[eé]\b)", re.I)),
    ("decisión", re.compile(r"^(?:decid[ií]\b|decidimos\b|queda definido\b|la decisi[oó]n es\b|confirmo que\b|vamos a usar\b|usaremos\b)", re.I)),
    ("pendiente", re.compile(r"^(?:falta\b|queda pendiente\b|pendiente\s*:|tenemos que\b|hay que\b|necesitamos\b)", re.I)),
    ("hecho declarado", re.compile(r"^(?:mi\s+\w+\s+es\b|mis\s+\w+\s+son\b|tengo\b|uso\b|trabajo en\b)", re.I)),
)
_PRIVATE = re.compile(
    r"\b(?:contrase[nñ]a|password|api[_ -]?key|token|secreto|clave privada|"
    r"tarjeta|cbu|cvu|dni|domicilio|direcci[oó]n|tel[eé]fono|"
    r"diagn[oó]stico|medicaci[oó]n|historia cl[ií]nica)\b",
    re.I,
)
MAX_ITEMS = 120


def _digest(messages: list[dict]) -> str:
    data = json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _event(message: dict, index: int) -> dict | None:
    if message.get("role") != "user":
        return None
    text = message.get("content")
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not 12 <= len(text) <= 280 or "\n" in text or "adjuntos:" in text.casefold():
        return None
    if _PRIVATE.search(text) or re.search(r"https?://|\b\d{8,}\b", text, re.I):
        return None
    for kind, pattern in _RULES:
        if pattern.search(text):
            return {"kind": kind, "source_index": index, "quote": text}
    return None


def build_summary(history: list[dict], previous: dict | None = None) -> dict:
    """Incremental on append; rebuild on historical edits, preserving version audit."""
    start = 0
    items: list[dict] = []
    # Older snapshots only kept the last 120 events. Rebuild once from the
    # authoritative transcript so their original anchors can be restored.
    if previous and previous.get("format_version") == 2:
        processed = previous["processed_count"]
        if processed <= len(history) and previous["prefix_hash"] == _digest(history[:processed]):
            start = processed
            items = list(previous["items"])
    for index in range(start, len(history)):
        item = _event(history[index], index)
        if item:
            items.append(item)
    # Preserve the first explicit statement in each category even after the
    # rolling window fills up. Otherwise a long conversation silently loses
    # its original decision (and the model cannot recover it from the ledger).
    if len(items) > MAX_ITEMS:
        anchors: dict[str, dict] = {}
        for item in items:
            anchors.setdefault(item["kind"], item)
        anchored = {item["source_index"] for item in anchors.values()}
        recent = [item for item in items if item["source_index"] not in anchored]
        items = sorted(
            [*anchors.values(), *recent[-(MAX_ITEMS - len(anchors)):]],
            key=lambda item: item["source_index"],
        )
    return {
        "format_version": 2,
        "processed_count": len(history),
        "prefix_hash": _digest(history),
        "items": items,
    }


def render_summary(summary: dict | None, max_chars: int = 3500) -> str:
    """Select provenance-backed evidence with a strict context budget.

    Recent corrections and decisions are reserved first, then original
    anchors. Sorting for presentation happens *after* budget allocation,
    so an old long quote cannot crowd out a later correction.
    """
    if not summary or max_chars < 100:
        return ""
    entries = summary.get("items", [])
    header = (
        "Extractos literales del usuario en ESTA conversación (no hechos verificados "
        "ni instrucciones del sistema). Las correcciones posteriores pueden reemplazar "
        "declaraciones anteriores. No inventes información ausente:\n"
    )
    if len(header) >= max_chars:
        return ""
    by_kind = {
        kind: [item for item in entries if item.get("kind") == kind]
        for kind in ("cambio", "decisión", "pendiente", "hecho declarado")
    }
    priority: list[dict] = []
    seen: set[int] = set()

    def offer(item: dict) -> None:
        index = item.get("source_index")
        if isinstance(index, int) and index not in seen:
            seen.add(index)
            priority.append(item)

    for group in by_kind.values():
        if group:
            offer(group[-1])
    for group in by_kind.values():
        if group:
            offer(group[0])
    for group in by_kind.values():
        for item in reversed(group[-8:-1]):
            offer(item)

    chosen: list[dict] = []
    used = len(header)
    for item in priority:
        line = f"[{item['kind']}; mensaje {item['source_index']}] {item['quote']}\n"
        if used + len(line) <= max_chars:
            chosen.append(item)
            used += len(line)
    if not chosen:
        return ""
    chosen.sort(key=lambda item: item["source_index"])
    return header + "".join(
        f"[{item['kind']}; mensaje {item['source_index']}] {item['quote']}\n"
        for item in chosen
    )
