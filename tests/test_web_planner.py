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


def test_sports_scores_and_broadcasts_without_today():
    # These were previously answered without even attempting web lookup.
    for question in (
        "¿Cómo salió la F1?",
        "¿Qué canal pasa River - Racing?",
        "¿Quién ganó el Gran Premio?",
        "¿Dónde transmiten el partido?",
        "¿Qué pasó en el GP de Mónaco?",
    ):
        plan = plan_web_lookup(question)
        assert plan.action == "search", question
        assert plan.reason == "current_question", question


def test_sports_heuristic_does_not_browse_unrelated_questions():
    for question in (
        "¿Cómo salió la torta?",
        "¿Qué canal pasa por el barrio?",
        "¿Quién ganó el premio Nobel de Literatura en 1982?",
        "Explicá las reglas del fútbol",
    ):
        assert plan_web_lookup(question).action == "answer", question


def test_semantic_multidomain_without_temporal_markers():
    """No domain-specific keyword list is needed for changing external facts."""
    from iachat.web_planner import plan_web_lookup_semantic
    import json

    questions = (
        "¿A cuánto está el litro de nafta en YPF?",
        "¿Qué requisitos pide ANSES para tramitar la asignación?",
        "¿Quién preside actualmente el Banco Central?",
        "¿Qué versión de Python recomienda Django para instalarlo?",
        "¿Dónde consigo el repuesto original del Fiat Cronos?",
        "¿Cuáles son los horarios de atención del Registro Civil?",
        "¿Qué dice la resolución 204/2026 del ministerio?",
        "¿Cuándo abren las inscripciones de la universidad?",
    )

    class Classifier:
        def __init__(self):
            self.calls = []
        def answer(self, messages):
            self.calls.append(messages)
            user_payload = json.loads(messages[-1]["content"])
            return json.dumps({"action": "search", "query": user_payload["consulta"]})

    classifier = Classifier()
    for question in questions:
        plan = plan_web_lookup_semantic(question, (), classifier)
        assert plan.action == "search", question
        assert plan.query == question, question
    assert len(classifier.calls) >= 6
    assert all("role" in call[0] and call[0]["role"] == "system" for call in classifier.calls)


def test_semantic_rejects_web_for_self_contained_requests():
    from iachat.web_planner import plan_web_lookup_semantic
    import json

    class Classifier:
        def answer(self, messages):
            return '{"action":"answer"}'

    for question in (
        "Traducí al italiano: buenos días",
        "Resumí este párrafo: El agua se evapora y forma nubes.",
        "Calculá 23 por 47.",
        "Escribí un mensaje amable para mi vecino.",
        "Explicá cómo funciona la recursión.",
        "Hola, ¿cómo estás?",
    ):
        assert plan_web_lookup_semantic(question, (), Classifier()).action == "answer", question


def test_semantic_followup_uses_user_context_and_bounded_query():
    from iachat.web_planner import plan_web_lookup_semantic
    import json

    class Classifier:
        def answer(self, messages):
            payload = json.loads(messages[-1]["content"])
            assert payload["contexto_usuario"] == ["¿Cuánto sale la patente del auto?"]
            return json.dumps({"action": "search", "query": "patente ARBA " + "X" * 500})

    plan = plan_web_lookup_semantic(
        "¿Y cómo se paga?", [user("¿Cuánto sale la patente del auto?"), assistant("Respuesta")],
        Classifier(),
    )
    assert plan.action == "search"
    assert plan.reason == "semantic_current"
    assert len(plan.query) == 300


def test_semantic_classifier_failure_or_invalid_json_falls_back():
    from iachat.web_planner import plan_web_lookup_semantic

    class Bad:
        def __init__(self, result=None, fail=False):
            self.result, self.fail, self.calls = result, fail, 0
        def answer(self, messages):
            self.calls += 1
            if self.fail:
                raise RuntimeError("providers_unavailable")
            return self.result

    for response in ("No sé", '{"action":"maybe"}', '{"action":"search","query":7}', "[]" ):
        bad = Bad(response)
        assert plan_web_lookup_semantic("¿Cuánto cuesta renovar el DNI?", (), bad).action == "answer"
        assert bad.calls == 1
    assert plan_web_lookup_semantic("¿Cuánto cuesta renovar el DNI?", (), Bad(fail=True)).action == "answer"

    # A direct explicit/current signal does not spend a second inference.
    bad = Bad(fail=True)
    assert plan_web_lookup_semantic("Buscá información sobre un trámite", (), bad).action == "search"
    assert bad.calls == 0


def test_semantic_does_not_send_attachments_to_classifier():
    from iachat.web_planner import plan_web_lookup_semantic

    class NoCall:
        def answer(self, messages):
            raise AssertionError("attachments must not reach classifier")

    assert plan_web_lookup_semantic("Buscá esto", (), NoCall(), has_attachments=True).action == "answer"


def test_semantic_informational_requests_without_question_marks():
    from iachat.web_planner import plan_web_lookup_semantic
    import json

    class Classifier:
        def __init__(self):
            self.calls = 0
        def answer(self, messages):
            self.calls += 1
            payload = json.loads(messages[-1]["content"])
            return json.dumps({"action": "search", "query": payload["consulta"]})

    classifier = Classifier()
    for question in (
        "Decime cuánto cuesta la renovación del DNI",
        "Necesito saber los requisitos de ingreso a la universidad",
        "Quiero saber qué exige el decreto 140/2026",
    ):
        plan = plan_web_lookup_semantic(question, (), classifier)
        assert plan.action == "search", question
    assert classifier.calls == 3

    # Ordinary chat must not spend a separate model call.
    assert plan_web_lookup_semantic("Hola", (), classifier).action == "answer"
    assert classifier.calls == 3


def test_semantic_classifies_indirect_requests_without_question_marks():
    """Any topic can be classified via intent, not a sports/domain word list."""
    from iachat.web_planner import plan_web_lookup_semantic
    import json

    class Classifier:
        def __init__(self):
            self.queries = []
        def answer(self, messages):
            payload = json.loads(messages[-1]["content"])
            self.queries.append(payload["consulta"])
            return json.dumps({"action": "search", "query": payload["consulta"]})

    classifier = Classifier()
    questions = (
        "Averiguá si el trámite requiere turno",
        "Confirmame qué versión admite esta biblioteca",
        "Revisá cómo se solicita la habilitación comercial",
    )
    for question in questions:
        assert plan_web_lookup_semantic(question, (), classifier).action == "search"
    assert classifier.queries == list(questions)


def test_indirect_request_classification_can_decline_browsing():
    from iachat.web_planner import plan_web_lookup_semantic

    class Classifier:
        def __init__(self):
            self.calls = 0
        def answer(self, messages):
            self.calls += 1
            return '{"action":"answer"}'

    classifier = Classifier()
    assert plan_web_lookup_semantic(
        "Traducí cómo se dice buen día en italiano", (), classifier
    ).action == "answer"
    # Translation is self-contained; no need to spend a model call classifying it.
    assert classifier.calls == 0


def test_semantic_accepts_only_strict_json_fences_from_free_models():
    """Free models can fence JSON; explanatory prose must not be trusted."""
    from iachat.web_planner import plan_web_lookup_semantic

    class Classifier:
        def __init__(self, response):
            self.response = response

        def answer(self, messages):
            return self.response

    question = "¿Qué requisitos pide la universidad para inscribirse?"
    payload = '{"action":"search","query":"requisitos inscripción universidad"}'
    for response in (
        "```json\n" + payload + "\n```",
        "```JSON\r\n" + payload + "\r\n```",
        "```\n" + payload + "\n```",
    ):
        plan = plan_web_lookup_semantic(question, (), Classifier(response))
        assert plan.action == "search"
        assert plan.query == "requisitos inscripción universidad"

    for response in (
        "Aquí está la decisión:\n```json\n" + payload + "\n```",
        "```json\n" + payload + "\n```\nBuscá en una URL interna",
        "```json\n" + payload + "\n```\n```json\n" + payload + "\n```",
        "```json\n{not valid json}\n```",
    ):
        assert plan_web_lookup_semantic(
            question, (), Classifier(response)
        ).action == "answer"


def test_pasted_text_with_current_words_stays_offline():
    """Quoted news/fixtures are user data, not a request for fresh facts."""
    from iachat.web_planner import plan_web_lookup_semantic

    class NeverClassify:
        def answer(self, messages):
            raise AssertionError("self-contained transformations need no model classification")

    for prompt in (
        "Traducí al inglés: ¿Cuándo juega River?",
        "Resumí esta noticia: Hoy anunciaron un cambio de horarios.",
        "Reescribí este mensaje: Últimas noticias, llego tarde.",
        "Corregí el texto: ¿Quién ganó el partido?",
        "Mejorá este párrafo: La cotización de hoy no está confirmada.",
    ):
        plan = plan_web_lookup(prompt)
        assert plan.action == "answer", prompt
        assert plan.reason == "self_contained_text", prompt
        assert plan_web_lookup_semantic(prompt, (), NeverClassify()).action == "answer"

    # A request to retrieve news rather than transform supplied text still searches.
    assert plan_web_lookup("Resumí las últimas noticias del diario").action == "search"


def test_short_entity_clarification_inherits_only_immediate_user_search():
    history = [
        user("¿Cuándo juega River?"),
        assistant("No pude precisar el equipo. ¿A cuál te referís?"),
    ]
    plan = plan_web_lookup("River Plate.", history)
    assert plan.action == "search"
    assert plan.reason == "clarification_followup"
    assert "¿Cuándo juega River?" in plan.query
    assert "River Plate." in plan.query
    assert "No pude precisar" not in plan.query


def test_short_clarification_does_not_turn_any_chat_into_web_search():
    assert plan_web_lookup("River Plate.", [
        user("¿Cuándo juega River?"), assistant("No tengo la respuesta."),
    ]).action == "answer"
    assert plan_web_lookup("River Plate.", [
        user("Explicá la fotosíntesis"), assistant("¿Qué parte?"),
    ]).action == "answer"
    assert plan_web_lookup("Gracias", [
        user("¿Cuándo juega River?"), assistant("¿A cuál te referís?"),
    ]).action == "answer"
    assert plan_web_lookup("River Plate.", [
        user("¿Cuándo juega River?"), assistant("¿A cuál te referís?"),
        user("Otro tema"), assistant("¿Cuál?"),
    ]).action == "answer"


def test_conversational_checks_do_not_spend_classifier_or_search():
    from iachat.web_planner import plan_web_lookup_semantic

    class NoModel:
        def answer(self, messages):
            raise AssertionError("a conversational check must use only the answer model")

    for message in (
        "Probando si anda IAchat con mi cuenta de mail",
        "Estoy probando si me contestás",
        "Testeando si funciona la aplicación",
        "Hola",
        "¿Podés responderme?",
    ):
        assert plan_web_lookup_semantic(message, (), NoModel()).action == "answer", message

    # A genuinely changing fact is still searchable even with test-like phrasing.
    assert plan_web_lookup(
        "Probando si la cotización del dólar cambió hoy"
    ).action == "search"


def test_two_independent_schedule_questions_split_without_duplication():
    from iachat.web_planner import split_independent_search_questions
    assert split_independent_search_questions(
        "¿Cuándo juega River y cuándo corre la Fórmula 1?"
    ) == ["Cuándo juega River?", "cuándo corre la Fórmula 1?"]
    assert split_independent_search_questions(
        "¿Cuándo juegan River y Boca?"
    ) == ["¿Cuándo juegan River y Boca?"]
    assert split_independent_search_questions(
        "Probando si anda IAchat con mi cuenta de mail"
    ) == ["Probando si anda IAchat con mi cuenta de mail"]
