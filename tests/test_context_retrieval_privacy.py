"""Regression tests for safe retrieval of old conversation turns."""
from iachat.context_retrieval import related_excerpts


def test_private_password_is_never_injected_into_model_context():
    history = [
        {"role": "user", "content": "La contraseña del servicio Atlas es secreto123."},
        {"role": "user", "content": "El servicio Atlas corre sobre PostgreSQL."},
    ]
    excerpts = related_excerpts(history, "¿Qué configuramos para el servicio Atlas?")
    assert len(excerpts) == 1
    assert "PostgreSQL" in excerpts[0]
    assert "secreto123" not in "\n".join(excerpts)


def test_sensitive_identifiers_urls_and_attachment_labels_are_excluded():
    history = [
        {"role": "user", "content": "Atlas se conecta a https://private.example.org/admin."},
        {"role": "user", "content": "El número de cuenta Atlas es 123456789012."},
        {"role": "user", "content": "Atlas Adjuntos: contrato.pdf"},
        {"role": "user", "content": "Atlas utiliza copias de respaldo diarias."},
    ]
    excerpts = related_excerpts(history, "¿Qué configuramos en Atlas?")
    assert len(excerpts) == 1
    assert "diarias" in excerpts[0]


def test_later_correction_outweighs_older_decision_with_similar_match():
    history = [
        {"role": "user", "content": "Para Atlas el motor Violeta será MotorAntiguo."},
        {"role": "assistant", "content": "MotorAntiguo confirmado."},
        {"role": "user", "content": "Corrijo: el motor Violeta de Atlas será MotorNuevo."},
    ]
    excerpts = related_excerpts(
        history, "¿Qué motor Violeta decidimos para Atlas?", max_items=1
    )
    assert len(excerpts) == 1
    assert "MotorNuevo" in excerpts[0]
    assert "MotorAntiguo" not in excerpts[0]
    assert "posición 2" in excerpts[0]


def test_never_recovers_assistant_claims_or_cross_conversation_text():
    history = [
        {"role": "assistant", "content": "Atlas usa un motor que inventé."},
        {"role": "user", "content": "Atlas utiliza motor LUCERO."},
    ]
    excerpts = related_excerpts(history, "¿Qué motor utiliza Atlas?")
    assert len(excerpts) == 1
    assert "LUCERO" in excerpts[0]
    assert "inventé" not in excerpts[0]


def test_retrieval_respects_strict_character_budget():
    history = [
        {"role": "user", "content": "Atlas motor " + "z" * 1200},
        {"role": "user", "content": "Atlas motor " + "y" * 1200},
        {"role": "user", "content": "Atlas motor " + "x" * 1200},
    ]
    excerpts = related_excerpts(history, "¿Qué motor tiene Atlas?", max_items=3, max_chars=150)
    assert len(excerpts) <= 3
    assert sum(len(item) for item in excerpts) <= 150


def test_unlabeled_api_credentials_and_one_time_codes_are_not_retrieved():
    history = [
        {"role": "user", "content": "Atlas usa ghp_AAAAAAAAAAAAAAAAAAAA en su repositorio."},
        {"role": "user", "content": "El PIN del proyecto Atlas es 4321."},
        {"role": "user", "content": "Atlas tiene código de verificación 7654."},
        {"role": "user", "content": "El proyecto Atlas utiliza PostgreSQL."},
    ]
    excerpts = related_excerpts(history, "¿Qué usa el proyecto Atlas?")
    assert len(excerpts) == 1
    assert "PostgreSQL" in excerpts[0]
    assert "ghp_" not in excerpts[0]
    assert "4321" not in excerpts[0]
    assert "7654" not in excerpts[0]


def test_long_multiline_turn_recovers_safe_fact_without_private_lines():
    filler = "Texto de relleno sin relación con la pregunta.\n" * 210
    history = [{
        "role": "user",
        "content": (
            filler
            + "La contraseña del motor Violeta de Atlas es secreto123.\n"
            + "Decidimos usar motor LUCERO para Violeta en Atlas.\n"
            + "Atlas Adjuntos: documento-privado.pdf"
        ),
    }]
    excerpts = related_excerpts(
        history, "¿Qué motor Violeta elegimos para Atlas?", max_chars=250
    )
    assert len(excerpts) == 1
    assert "motor LUCERO" in excerpts[0]
    assert "línea " in excerpts[0]
    assert "secreto123" not in excerpts[0]
    assert "documento-privado.pdf" not in excerpts[0]
    assert sum(len(item) for item in excerpts) <= 250


def test_long_multiline_turn_with_only_sensitive_matches_returns_nothing():
    filler = "Relleno completamente ajeno al asunto.\n" * 220
    history = [{"role": "user", "content":
                filler + "La contraseña del motor Violeta de Atlas es secreto123."}]
    assert related_excerpts(history, "¿Qué motor Violeta usa Atlas?") == []


def test_long_multiline_late_correction_outranks_earlier_decision():
    history = [
        {"role": "user", "content": "El motor Violeta de Atlas será ANTIGUO."},
        {"role": "assistant", "content": "El motor de Atlas es INVENTADO."},
        {"role": "user", "content": (
            "Relleno sin relación.\n" * 350
            + "Corrijo: el motor Violeta de Atlas será NUEVO."
        )},
    ]
    excerpts = related_excerpts(
        history, "¿Qué motor Violeta elegimos para Atlas?", max_items=1
    )
    assert len(excerpts) == 1
    assert "NUEVO" in excerpts[0]
    assert "ANTIGUO" not in excerpts[0]
    assert "INVENTADO" not in excerpts[0]
