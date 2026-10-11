from iachat.context_retrieval import related_excerpts


def test_older_excerpt_matches_specific_words_not_generic_questions():
    history = [
        {"role": "user", "content": "Compré una bicicleta plegable verde para la ciudad."},
        {"role": "assistant", "content": "Una bicicleta plegable es práctica."},
        {"role": "user", "content": "Me interesa cocinar pizza casera."},
    ]
    found = related_excerpts(history, "¿Qué dije de mi bicicleta plegable?")
    assert len(found) == 1
    assert "bicicleta plegable verde" in found[0]
    assert "pizza" not in found[0]


def test_excerpts_do_not_treat_assistant_messages_as_user_facts():
    history = [
        {"role": "assistant", "content": "La contraseña del proyecto es falsa."},
        {"role": "user", "content": "Hablemos de películas policiales."},
    ]
    assert related_excerpts(history, "¿Qué contraseña dije del proyecto?") == []


def test_retrieval_is_bounded_and_requires_subject_terms():
    history = [{"role": "user", "content": "bicicleta " * 70} for _ in range(10)]
    found = related_excerpts(history, "¿Qué bicicleta hablamos antes?", max_items=2, max_chars=300)
    assert len(found) == 2
    assert sum(len(x.split(": ", 1)[1]) for x in found) <= 300
    assert related_excerpts(history, "¿Qué dijimos antes?") == []


def test_retrieval_handles_accents_and_simple_plurals():
    messages = [{"role": "user", "content": "Las películas de misterio me interesan."}]
    found = related_excerpts(messages, "¿Qué película misteriosa mencioné?")
    assert len(found) == 1


def test_simple_synonyms_recover_older_message_without_inventing_it():
    history = [{"role": "user", "content": "Dejé el auto en el garaje."}]
    found = related_excerpts(history, "¿Dónde dejé el coche?")
    assert len(found) == 1
    assert "Dejé el auto en el garaje" in found[0]


def test_unrelated_concepts_do_not_match():
    history = [{"role": "user", "content": "El teléfono quedó cargando."}]
    assert related_excerpts(history, "¿Dónde guardé el coche?") == []
