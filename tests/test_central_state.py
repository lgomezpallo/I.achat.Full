from iachat.central_state import (
    ConversationState, ask_clarification, clear_topic, resolve_topic, set_topic,
)
import pytest


def test_reference_uses_only_verified_active_topic():
    state = ConversationState()
    assert resolve_topic("¿Qué quedó pendiente ahí?", state).status == "clarify"
    set_topic(state, "Montevideo y Corrientes")
    result = resolve_topic("¿Qué quedó pendiente ahí?", state)
    assert (result.status, result.topic) == ("resolved", "Montevideo y Corrientes")


def test_no_reference_does_not_force_old_topic():
    state = ConversationState(active_topic="Obra 1058")
    assert resolve_topic("¿Cuánto es dos más dos?", state).status == "unrelated"


def test_conversations_have_independent_state():
    first = ConversationState()
    second = ConversationState()
    set_topic(first, "Obra 1058")
    first.facts["permiso"] = "pendiente"
    assert second.active_topic is None
    assert second.facts == {}


def test_pending_question_cleared_by_topic_update():
    state = ConversationState()
    ask_clarification(state, "¿Cuál obra?")
    assert state.pending_question == "¿Cuál obra?"
    set_topic(state, "Obra 1058")
    assert state.pending_question is None
    clear_topic(state)
    assert state.active_topic is None


def test_empty_topic_is_rejected():
    with pytest.raises(ValueError):
        set_topic(ConversationState(), "   ")
