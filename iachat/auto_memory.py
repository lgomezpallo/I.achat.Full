"""Conservative automatic memory capture without extra model calls.

Only stable, first-person preference statements are eligible. Everything else
remains in chat history until a stronger, auditable extraction pipeline exists.
"""
from __future__ import annotations
import re
from uuid import uuid4

_PREFIX = re.compile(
    r"^(?:yo\s+)?(?:prefiero|me gusta|me gustan|no me gusta|no me gustan|"
    r"quiero que (?:me )?(?:respondas|hables|expliques)|"
    r"me resulta (?:mejor|más cómodo))\b",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(
    r"\b(?:contraseña|clave|token|api key|secreto|tarjeta|cuenta bancaria|"
    r"cbu|cv[u]|dni|dirección|domicilio|teléfono|salud|diagnóstico|"
    r"enfermedad|medicación|embarazo|religión|partido político|"
    r"voto|sexualidad|deuda|sueldo|ingreso|finanzas|banco)\b",
    re.IGNORECASE,
)


def candidate(text: str) -> str | None:
    """Extract one high-confidence preference from a standalone user statement."""
    value = re.sub(r"\s+", " ", text).strip()
    if not 12 <= len(value) <= 220:
        return None
    if "\n" in text or len(re.split(r"[.!?]", value)) > 2:
        return None
    if not _PREFIX.match(value):
        return None
    if _SENSITIVE.search(value) or re.search(r"\d|@|https?://", value, re.I):
        return None
    return value.rstrip(" .")


def learn(store, owner: str, text: str, project: str = "") -> bool:
    value = candidate(text)
    if not value:
        return False
    def normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().rstrip(" .!?¿¡").casefold()
    existing = {normalize(m["content"]) for m in store.list_memories(owner, project)}
    if normalize(value) in existing:
        return False
    store.save_automatic_memory(str(uuid4()), value, owner, project)
    return True
