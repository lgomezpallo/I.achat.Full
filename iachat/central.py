"""Deterministic conversation decisions, independent of model providers.

Central returns an explicit decision. It never invents an answer to an open
question: unsupported requests are delegated to the model.
"""
from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class Decision:
    action: str  # "reply", "clarify", or "delegate"
    response: str = ""
    reason: str = ""


def decide(text: str, *, today: date | None = None) -> Decision:
    """Handle only unambiguous, safe conversational operations locally."""
    message = " ".join(text.strip().split())
    if not message:
        return Decision("clarify", "¿Qué querés consultar?", "empty_input")

    # Strict full matches avoid accidentally answering part of a larger request.
    if re.fullmatch(r"(hola|buenas|buen día|buen dia|buenas tardes|buenas noches)[!. ]*", message, re.I):
        return Decision("reply", "¡Hola! ¿En qué te puedo ayudar?", "greeting")

    if re.fullmatch(r"(gracias|muchas gracias|mil gracias)[!. ]*", message, re.I):
        return Decision("reply", "¡De nada!", "thanks")

    if re.fullmatch(r"(qué fecha es hoy|que fecha es hoy|cuál es la fecha de hoy|cual es la fecha de hoy)[?¿!. ]*", message, re.I):
        if today is None:
            return Decision("delegate", reason="date_source_missing")
        return Decision("reply", f"Hoy es {today.strftime('%d/%m/%Y')}.", "verified_date")

    return Decision("delegate", reason="open_request")
