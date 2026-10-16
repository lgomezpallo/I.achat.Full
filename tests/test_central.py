from datetime import date
from iachat.central import decide


def test_greeting_is_local():
    decision = decide("¡Hola!")  # punctuation not in strict matcher: delegate safely
    assert decision.action == "delegate"
    assert decide("Hola").action == "reply"


def test_thanks_are_local():
    assert decide("Muchas gracias").action == "reply"


def test_empty_input_asks_for_clarification():
    assert decide("  ").action == "clarify"


def test_verified_date_is_local():
    assert decide("¿Qué fecha es hoy?", today=date(2026, 10, 16)).response == "Hoy es 16/10/2026."


def test_date_without_source_is_delegated():
    assert decide("¿Qué fecha es hoy?").action == "delegate"


def test_open_or_mixed_requests_never_get_canned_answers():
    for message in ("Hola, explicame física", "Gracias, pero no funciona", "¿Qué ves en esta foto?", "¿Qué quedó pendiente en la obra?"):
        assert decide(message).action == "delegate"
