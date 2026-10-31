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
