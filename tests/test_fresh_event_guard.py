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
