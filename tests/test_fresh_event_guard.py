from datetime import date

from iachat.fresh_event_guard import reject_stale_next_event_answer


def test_past_race_cannot_be_upcoming():
    question = "¿Cuándo juega River y cuándo corre la próxima carrera de Fórmula 1?"
    answer = (
        "River juega el 1 de noviembre de 2026.\n"
        "Próxima carrera de Fórmula 1: domingo 25 de octubre de 2026."
    )
    result = reject_stale_next_event_answer(
        question, answer, today=date(2026, 10, 30)
    )
    assert "25 de octubre de 2026" not in result
    assert "no voy a presentarla como futura" in result


def test_future_race_is_untouched():
    answer = "Próxima carrera: 1 de noviembre de 2026."
    assert reject_stale_next_event_answer(
        "¿Cuándo corre la próxima carrera?", answer, today=date(2026, 10, 30)
    ) == answer


def test_historical_context_not_modified_if_not_upcoming():
    answer = "La carrera del 25 de octubre de 2026 ya terminó."
    assert reject_stale_next_event_answer(
        "Contame sobre Fórmula 1", answer, today=date(2026, 10, 30)
    ) == answer


def test_unparseable_or_absent_date_not_falsely_rejected():
    answer = "Próxima carrera: no está confirmada."
    assert reject_stale_next_event_answer(
        "¿Cuándo corre la próxima carrera?", answer, today=date(2026, 10, 30)
    ) == answer


def test_upcoming_partido_numeric_past_date_is_rejected():
    assert "no voy a presentarla como futura" in reject_stale_next_event_answer(
        "¿Cuándo es el próximo partido?",
        "El próximo partido será el 25/10/2026 a las 18:00.",
        today=date(2026, 10, 30),
    )


def test_upcoming_concert_iso_past_date_is_rejected_without_label():
    assert "no voy a presentarla como futura" in reject_stale_next_event_answer(
        "¿Cuándo es el siguiente recital?",
        "Será el 2026-10-25.",
        today=date(2026, 10, 30),
    )


def test_unrelated_historical_date_does_not_cancel_future_claim():
    answer = (
        "La carrera anterior fue el 25 de octubre de 2026.\n"
        "La próxima carrera será el 1 de noviembre de 2026."
    )
    assert reject_stale_next_event_answer(
        "¿Cuándo es la próxima carrera?", answer, today=date(2026, 10, 30)
    ) == answer


def test_upcoming_event_today_not_rejected_on_date_alone():
    answer = "El próximo evento es hoy, 30/10/2026 a las 23:00."
    assert reject_stale_next_event_answer(
        "¿Cuándo es el próximo evento?", answer, today=date(2026, 10, 30)
    ) == answer
