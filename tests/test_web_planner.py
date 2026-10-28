"""Offline tests: no provider keys, internet, or real conversations required."""
from iachat.web_planner import plan_web_lookup


def user(content):
    return {"role": "user", "content": content}


def assistant(content):
    return {"role": "assistant", "content": content}


def test_current_question_requests_evidence():
    plan = plan_web_lookup("¿Cuándo juega River?")
    assert (plan.action, plan.reason) == ("search", "current_question")
    assert "River" in plan.query


def test_explicit_research_is_not_limited_to_news():
    plan = plan_web_lookup("Buscá documentación de FastAPI")
    assert plan.action == "search"
    assert plan.reason == "explicit_search"


def test_followup_uses_previous_user_question_as_query_context():
    history = [user("¿Cuándo juega River?"), assistant("No tengo datos")]
    plan = plan_web_lookup("¿Y dónde lo pasan?", history)
    assert plan.action == "search"
    assert plan.reason == "contextual_followup"
    assert "River" in plan.query
    assert "dónde lo pasan" in plan.query


def test_two_referential_followups_keep_original_subject():
    history = [
        user("¿Cuándo juega River?"),
        assistant("Respuesta"),
        user("¿Y dónde lo pasan?"),
        assistant("Respuesta"),
    ]
    plan = plan_web_lookup("¿Y el horario?", history)
    assert plan.action == "search"
    assert "River" in plan.query


def test_unrelated_new_topic_does_not_inherit_old_search():
    history = [
        user("¿Cuándo juega River?"),
        assistant("Respuesta"),
        user("¿Cómo cocinar arroz?"),
        assistant("Respuesta"),
    ]
    assert plan_web_lookup("¿Y dónde?", history).action == "answer"


def test_assistant_text_cannot_trigger_user_web_search():
    history = [assistant("Hoy se publica un resultado")]
    assert plan_web_lookup("¿Y dónde?", history).action == "answer"


def test_no_search_for_thanks_or_timeless_questions():
    history = [user("¿Cuándo juega River?")]
    assert plan_web_lookup("Gracias", history).action == "answer"
    assert plan_web_lookup("Explicame qué es una variable", history).action == "answer"


def test_attachment_does_not_trigger_untrusted_web_access():
    plan = plan_web_lookup("Buscá esta información", has_attachments=True)
    assert plan.action == "answer"


def test_query_is_bounded():
    plan = plan_web_lookup("Buscá " + "documentación " * 100)
    assert plan.action == "search"
    assert len(plan.query) <= 300


def test_old_conversation_does_not_trigger_lookup():
    history = [user("¿Cuándo juega River?")] + [
        assistant("Respuesta"), user("Otro tema")
    ] * 6
    assert plan_web_lookup("¿Y dónde?", history).action == "answer"
