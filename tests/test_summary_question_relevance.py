"""Question-aware, provenance-backed selection of old conversation decisions."""
from iachat.conversation_summary import build_summary, render_summary


def _history():
    messages = []
    for index in range(90):
        if index == 44:
            text = "Decidimos usar el motor Orión para el proyecto Violeta."
        else:
            text = f"Decidimos revisar el módulo general número {index}."
        messages.append({"role": "user", "content": text})
    return messages


def test_question_recovers_middle_decision_outside_generic_summary_window():
    summary = build_summary(_history())
    generic = render_summary(summary, max_chars=440)
    focused = render_summary(
        summary, max_chars=440,
        question="¿Qué motor elegimos para Violeta?",
    )
    assert "motor Orión" not in generic
    assert "motor Orión" in focused
    assert "mensaje 44" in focused
    assert len(focused) <= 440


def test_unrelated_question_does_not_invent_matching_evidence():
    summary = build_summary(_history())
    baseline = render_summary(summary, max_chars=440)
    unrelated = render_summary(
        summary, max_chars=440,
        question="¿Qué telescopio instalamos en Marte?",
    )
    assert unrelated == baseline
    assert "telescopio" not in unrelated
    assert "Marte" not in unrelated


def test_question_matching_keeps_user_corrections_and_bounded_context():
    history = _history()
    history[45] = {"role": "user", "content": "Corrijo: el motor Orión de Violeta será solar."}
    summary = build_summary(history)
    selected = render_summary(
        summary, max_chars=500,
        question="¿Qué motor usa Violeta?",
    )
    assert "motor Orión" in selected
    assert "será solar" in selected
    assert len(selected) <= 500
