"""Optional G.O. proposal adapter for the shared IAchat chat engine.

Only the labor instance may use the existing G.O. PostgreSQL approval ledger.
No new business schema, SQL generator, or independent inference engine.
Disabled by default until an isolated deployment is audited.
"""
from __future__ import annotations

import json
import os
from uuid import UUID


def enabled() -> bool:
    return (os.getenv("IACHAT_PROFILE", "personal").strip().lower() == "go-ute"
            and os.getenv("GO_WORK_WRITE_ENABLED") == "1")


def instruction() -> str | None:
    if not enabled():
        return None
    return (
        "En esta instancia laboral, respondé SOLO con un objeto JSON válido, "
        "sin markdown, con go_intent='v1'. Para consultas, preguntas generales "
        "o ambigüedades: intent='conversation', reply=respuesta en español. "
        "Para proponer una categoría: intent='define_type', record_type y schema. "
        "Para proponer una novedad: intent='record', record_type, budget y values. "
        "Para proponer una corrección: intent='correct', record_type, budget, "
        "replaces (UUID del evento oficial vigente) y values (sólo cambios). "
        "Usá exclusivamente categorías y atributos que figuren en la evidencia "
        "oficial; si falta una categoría, proponé define_type primero. "
        "No inventes obras, IDs, fechas, estados ni cantidades. "
        "Si hay dudas, respondé conversation y pedí el dato. "
        "Distinguí previsto de realizado. "
        "NUNCA afirmes que una propuesta está confirmada ni escribas SQL. "
        "La aplicación validará y pedirá confirmación por separado."
    )


def _ledger():
    if not enabled() or not os.getenv("GO_DATABASE_URL", "").strip():
        raise RuntimeError("go_work_write_not_configured")
    try:
        from go_ute import flexible
    except ImportError as exc:
        raise RuntimeError("go_work_approval_engine_missing") from exc
    return flexible


def decide_in_conversation(message: str, history: list[dict]) -> str | None:
    """Resolve only the immediately preceding, server-owned proposal.

    A UUID supplied by another user, conversation, or an older turn is not
    authorization. Never use the global G.O. chat-turns fallback.
    """
    if not enabled():
        return None
    import re

    # Natural confirmations are safe only for the immediate pending proposal
    # in the authenticated, server-loaded conversation. Never consult the
    # G.O. ledger's global last-turn fallback (it is not user-scoped).
    short_yes = re.fullmatch(r"\s*(?:s[ií]|dale|ok(?:ay)?|confirmo|confirm[aá]r?)\s*[.!]?\s*", message, re.I)
    short_no = re.fullmatch(r"\s*(?:no|descarto|descart[aá]r?|cancel[aá]r?)\s*[.!]?\s*", message, re.I)
    explicit = re.match(r"^\s*(?:confirmo|confirmar|descarto|descartar)\s+propuesta\b", message, re.I)
    if not (short_yes or short_no or explicit):
        return None
    last = history[-1] if history else None
    if short_yes or short_no:
        if not isinstance(last, dict) or last.get("role") != "assistant":
            return None
        proposal_id = last.get("go_proposal_id")
        try:
            proposal_id = str(UUID(proposal_id))
        except (ValueError, TypeError, AttributeError):
            return None
        return _ledger().decide(proposal_id, bool(short_yes))["reply"]
    ledger = _ledger()
    decision = ledger.decision_from_message(message)
    if decision is None:
        return "Para decidir, indicá 'Confirmo propuesta <UUID>' o 'Descarto propuesta <UUID>'."
    proposal_id, approved = decision
    if not isinstance(last, dict) or last.get("role") != "assistant" or last.get("go_proposal_id") != proposal_id:
        return "Esa propuesta no está pendiente en esta conversación. No se modificaron registros."
    return ledger.decide(proposal_id, approved)["reply"]

def interpret_model_answer(raw: str, message: str, *, attachments: bool = False) -> tuple[str, str | None]:
    """Use the *same* IAchat model response to propose, never to commit.

    Plain text and malformed JSON remain conversation, not database actions.
    """
    if not enabled():
        return raw, None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return raw, None
    if not isinstance(parsed, dict) or parsed.get("go_intent") != "v1":
        return raw, None
    intent = parsed.get("intent")
    if intent == "conversation":
        reply = parsed.get("reply")
        if isinstance(reply, str) and 0 < len(reply.strip()) <= 4000:
            return reply, None
        return "Necesito una aclaración para responder; no modifiqué registros.", None
    if intent not in {"record", "correct", "define_type"}:
        return "No pude interpretar una propuesta segura. No se modificaron registros.", None
    if attachments:
        return "Analicé el adjunto, pero su asociación o registro requiere una confirmación documental específica; no modifiqué registros.", None
    ledger = _ledger()
    try:
        result = ledger.stage(parsed, message)
    except ledger.InvalidProposal as exc:
        return str(exc) + " No se modificaron registros oficiales.", None
    if result.get("phase") != "flexible_pending":
        return "No se pudo preparar la propuesta; no se modificaron registros.", None
    identifier = result.get("proposal_id")
    try:
        identifier = str(UUID(identifier))
    except (TypeError, ValueError, AttributeError):
        raise RuntimeError("go_work_invalid_proposal_id")
    return result["reply"], identifier
