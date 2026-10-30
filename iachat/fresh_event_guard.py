"""Reject demonstrably past dates presented as upcoming events.

This guard does not guess the next event or treat RSS as fact. It only blocks
claims that contradict the current calendar date. Dates are interpreted in
Argentina's locale; the date itself is not a source of event confirmation.
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
_TEXT_DATE = re.compile(
    r"\b([0-3]?\d)\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+(?:de\s+)?(20\d{2})\b", re.I,
)
_NUMERIC_DATE = re.compile(r"(?<!\d)([0-3]?\d)[/-]([01]?\d)[/-](20\d{2})(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(20\d{2})-([01]?\d)-([0-3]?\d)(?!\d)")
_UPCOMING_QUESTION = re.compile(
    r"\b(?:pr[oó]xim[oa]s?|siguientes?|"
    r"cu[aá]ndo\s+(?:juega|corre|vuelve(?:n)?\s+a))\b", re.I,
)
_UPCOMING_ANSWER = re.compile(r"\b(?:pr[oó]xim[oa]s?|siguientes?)\b", re.I)
_PAST_CONTEXT = re.compile(
    r"\b(?:pasad[oa]s?|anterior(?:es)?|hist[oó]ric[oa]s?|"
    r"ya\s+(?:pas[oó]|termin[oó]|ocurri[oó]))\b", re.I,
)
_REJECTION = (
    "No pude confirmar de forma confiable la próxima fecha. "
    "La información obtenida contiene una fecha que ya pasó, "
    "así que no voy a presentarla como futura. "
    "Necesito fuentes actualizadas para responder con precisión."
)


def _dates(text: str) -> list[date]:
    found: list[tuple[int, date]] = []
    for match in _TEXT_DATE.finditer(text):
        try:
            found.append((match.start(), date(
                int(match.group(3)), _MONTHS[match.group(2).lower()],
                int(match.group(1)),
            )))
        except ValueError:
            continue
    for match in _NUMERIC_DATE.finditer(text):
        try:
            found.append((match.start(), date(
                int(match.group(3)), int(match.group(2)), int(match.group(1)),
            )))
        except ValueError:
            continue
    for match in _ISO_DATE.finditer(text):
        try:
            found.append((match.start(), date(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
            )))
        except ValueError:
            continue
    return [value for _, value in sorted(found)]


def reject_stale_next_event_answer(
    question: str, answer: str, *, today: date | None = None,
) -> str:
    """Fail closed when an upcoming event is assigned a date already past.

    For a labelled next event, inspect the first date after that label in its
    sentence, not unrelated historical paragraphs. If the answer omits labels,
    inspect an unambiguous single date only. No domain-specific event names.
    """
    if not _UPCOMING_QUESTION.search(question):
        return answer
    today = today or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    labels = list(_UPCOMING_ANSWER.finditer(answer))
    for label in labels:
        excerpt = answer[label.end():label.end() + 180].split("\n", 1)[0]
        excerpt = re.split(r"(?<!\d)\.\s+", excerpt, maxsplit=1)[0]
        dates = _dates(excerpt)
        if dates and dates[0] < today and not _PAST_CONTEXT.search(excerpt[:50]):
            return _REJECTION
    if not labels:
        dates = _dates(answer)
        if len(dates) == 1 and dates[0] < today and not _PAST_CONTEXT.search(answer):
            return _REJECTION
    return answer
