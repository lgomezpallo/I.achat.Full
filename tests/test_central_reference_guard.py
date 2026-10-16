from iachat.central_state import ConversationState, resolve_topic


def test_demonstratives_with_nouns_do_not_force_clarification():
    state = ConversationState()
    for text in ('¿Qué significa esa palabra?', '¿Qué pasó este año?', '¿Dónde queda ese lugar?'):
        assert resolve_topic(text, state).status == 'unrelated'
