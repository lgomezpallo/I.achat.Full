"""Conservative guard against labeling an already completed race as upcoming.

A strict detector only: reject unsupported 'next race' claims instead of
attempting to hallucinate a replacement calendar. No external dependencies.
"""
from __future__ import annotations

import re
from datetime import datetime, date
from zoneinfo import ZoneInfo

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_DATE = re.compile(
    r"\b([0-3]?\d)\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+(?:de\s+)?(20\d{2})\b", re.I
)
_NEXT_RACE = re.compile(
    r"(?:pr[oó]xim[ao]\s+(?:carrera|gran\s+premio|gp)|"
    r"siguiente\s+(?:carrera|gran\s+premio|gp))", re.I
)


def reject_stale_next_event_answer(question: str, answer: str, *,
                                   today: date | None = None) -> str:
    """Fail closed on explicit past dates in a claimed upcoming racing event.

    Check only the next-race subsection following its label, not historical
    context elsewhere. If detected, suppress the untrustworthy response:
    preserving other claims would risk repeating the stale event in summaries.
    """
    if not re.search(r"pr[oó]xim[ao]\s+carrera|cu[aá]ndo\s+corre|"
                     r"pr[oó]xim[ao]\s+(?:gp|gran\s+premio)", question, re.I):
        return answer
    today = today or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    section = _NEXT_RACE.search(answer)
    if not section:
        return answer
    # At most the first 450 chars after the section label: avoid citations and
    # mentions of distant past events in later unrelated paragraphs.
    excerpt = answer[section.end():section.end() + 450]
    for match in _DATE.finditer(excerpt):
        try:
            event_date = date(int(match.group(3)), _MONTHS[match.group(2).lower()],
                              int(match.group(1)))
        except ValueError:
            continue
        if event_date < today:
            return (
                "No pude confirmar de forma confiable la próxima carrera. "
                "La información obtenida contiene una fecha que ya pasó, "
                "así que no voy a presentarla como futura. "
                "Necesito fuentes actualizadas para responder con precisión."
            )
    return answer
