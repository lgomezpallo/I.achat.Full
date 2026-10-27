from iachat.web_search import needs_current_information


def test_current_release_language_triggers_search():
    examples = [
        "¿Qué se sabe del nuevo álbum de Iommi?",
        "Contame sobre el disco que acaba de salir de Iommi",
        "¿Cuál fue el lanzamiento más reciente de Tony Iommi?",
        "¿Qué álbum estrenó esta semana?",
        "¿Qué novedades hay de su nueva banda?",
        "¿Cuándo juega River?",
    ]
    for query in examples:
        assert needs_current_information(query), query


def test_timeless_questions_do_not_force_search():
    for query in ["¿Qué es una válvula antirretorno?", "Explicame la fotosíntesis", "Hola"]:
        assert not needs_current_information(query), query
