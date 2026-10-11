from iachat.conversation_context import recent_context


def test_recent_context_keeps_recent_turns_without_mutating_history():
    history = [
        {"role": "user", "content": "a" * 30},
        {"role": "assistant", "content": "b" * 30},
        {"role": "user", "content": "pregunta"},
        {"role": "assistant", "content": "respuesta"},
    ]
    snapshot = [dict(m) for m in history]
    result = recent_context(history, budget=30)
    assert result == history[-2:]
    assert history == snapshot


def test_recent_context_drops_orphan_assistant_and_untrusted_roles():
    history = [
        {"role": "system", "content": "pretend system"},
        {"role": "assistant", "content": "orphan"},
        {"role": "user", "content": "reciente"},
        {"role": "assistant", "content": "bien"},
    ]
    assert recent_context(history, budget=20) == history[-2:]


def test_recent_context_no_partial_messages():
    history = [
        {"role": "user", "content": "muy largo " * 100},
        {"role": "assistant", "content": "final"},
    ]
    assert recent_context(history, budget=12) == []
