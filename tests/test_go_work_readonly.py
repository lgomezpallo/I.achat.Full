"""No-network contract tests for the read-only G.O. ledger adapter."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from iachat import go_work_context as work
import iachat.app as app_module
from iachat.store import ConversationStore


class Result:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeReadOnlyConnection:
    def __init__(self, *, writable=False, can_create_schema=False, can_create_database=False):
        self.statements = []
        self.writable = writable
        self.can_create_schema = can_create_schema
        self.can_create_database = can_create_database

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if sql.startswith("SHOW transaction_read_only"):
            return Result(("on",))
        if "FROM pg_class c" in sql:
            return Result((self.writable,))
        if "has_schema_privilege" in sql:
            return Result((self.can_create_schema,))
        if "has_database_privilege" in sql:
            return Result((self.can_create_database,))
        if sql.startswith("SELECT t.nombre,t.version,t.esquema FROM go_record_types t"):
            return Result(many=[
                ("medicion", 2, {"horas": {"tipo": "numero", "unidad": "h", "obligatorio": True}}),
                ("nota", 1, {"detalle": {"tipo": "texto"}}),
            ])
        if sql == "SELECT COUNT(*) FROM obras":
            return Result((3,))
        if sql.startswith("SELECT estado,COUNT(*) FROM obras"):
            return Result(many=[("en_ejecucion", 2), ("pendiente", 1)])
        if sql.startswith("SELECT presupuesto,direccion,estado FROM obras WHERE direccion ILIKE"):
            assert params and len(params) == 1
            if params == ("%Alsina 354%",):
                return Result(many=[("1190", "Alsina 354", "en_ejecucion")])
            if params == ("%Rivadavia y Rodríguez Peña%",):
                return Result(many=[
                    ("1093", "Rivadavia y Rodríguez Peña", "en_ejecucion"),
                    ("1993", "Av. Rivadavia y Rodríguez Peña", "pendiente"),
                ])
            return Result(many=[])
        if sql.startswith("SELECT presupuesto,direccion,estado FROM obras"):
            return Result(many=[
                ("1093", "Rivadavia y Rodríguez Peña", "en_ejecucion"),
                ("1190", "Alsina 354", "en_ejecucion"),
                ("1192", "Suipacha 671", "pendiente"),
            ])
        if sql.startswith("SELECT id,direccion,estado FROM obras"):
            assert params in (("1093",), ("1190",))
            if params == ("1190",):
                return Result(("work-1190", "Alsina 354", "en_ejecucion"))
            return Result(("work-uuid", "Rivadavia y Rodríguez Peña", "pendiente"))
        if sql.startswith("SELECT e.id,e.tipo,e.version,e.datos"):
            assert params in (("work-uuid",), ("work-1190",))
            if params == ("work-1190",):
                return Result(many=[
                    ("event-1190", "medicion", 1, {"horas": 6, "estado": "previsto"}),
                ])
            return Result(many=[
                ("event-uuid", "medicion", 2, {"horas": 8, "estado": "realizado"}),
            ])
        return Result()


def test_scoped_ledger_read_uses_parameterized_selects_only(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-connection-not-real")
    connection = FakeReadOnlyConnection()
    seen = []
    def connect(dsn, **kwargs):
        seen.append((dsn, kwargs))
        return connection
    context = work.official_context("¿Qué se registró en la obra 1093?", connect=connect)
    assert '"presupuesto": "1093"' in context
    assert '"horas": 8' in context
    assert '"estado": "realizado"' in context
    assert '"estado": "pendiente"' in context
    assert '"categorias_confirmadas"' in context
    assert '"nombre": "medicion"' in context
    assert '"version": 2' in context
    assert '"unidad": "h"' in context
    assert seen == [("test-connection-not-real", {"connect_timeout": 5})]
    assert all(
        sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
        for sql, _ in connection.statements
    )
    assert any("NOT EXISTS" in sql and "LIMIT 8" in sql for sql, _ in connection.statements)


def test_general_work_question_reads_bounded_official_overview(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "¿Cuántas obras hay y cuáles están pendientes?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"total_obras": 3' in result
    assert '"cantidad": 2' in result
    assert '"presupuesto": "1192"' in result
    assert '"otros_registros_consultados": false' in result
    assert any("LIMIT 20" in sql for sql, _ in connection.statements)
    assert any("LIMIT 30" in sql for sql, _ in connection.statements)
    assert all(
        sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
        for sql, _ in connection.statements
    )


def test_confirmed_categories_are_bounded_readonly_metadata(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "¿Qué categorías de registros puedo utilizar?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "categorias_confirmadas"' in result
    assert '"nombre": "medicion"' in result
    assert '"version": 2' in result
    assert '"unidad": "h"' in result
    assert '"nombre": "nota"' in result
    assert '"sin_cambios_oficiales": true' in result
    assert all(
        sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
        for sql, _ in connection.statements
    )


def test_general_chat_without_work_reference_never_reads_postgres(monkeypatch):
    monkeypatch.delenv("GO_WORK_READONLY_DSN", raising=False)
    assert work.official_context("Hola, ¿cómo estás?") is None


def test_multiwork_query_keeps_each_budget_separate_and_bounded(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "Compará la medición de obra 1093 con obra 1190",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "comparacion_obras"' in result
    assert '"presupuesto": "1093"' in result
    assert '"presupuesto": "1190"' in result
    assert '"horas": 8' in result and '"horas": 6' in result
    assert '"max_registros_por_obra": 8' in result
    assert '"categorias_confirmadas"' in result
    assert '"nombre": "medicion"' in result
    scoped = [(sql, params) for sql, params in connection.statements
              if sql.startswith("SELECT id,direccion,estado FROM obras")]
    assert len(scoped) == 2
    assert {params for _, params in scoped} == {("1093",), ("1190",)}
    assert all(sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
               for sql, _ in connection.statements)


def test_readonly_adapter_refuses_writer_account_and_unbounded_comparison(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    with pytest.raises(work.WorkContextUnavailable, match="go_work_role_has_write_privileges"):
        work.official_context("obra 1093", connect=lambda *args, **kwargs: FakeReadOnlyConnection(writable=True))
    with pytest.raises(work.WorkContextUnavailable, match="go_work_role_has_write_privileges"):
        work.official_context("obra 1093", connect=lambda *args, **kwargs: FakeReadOnlyConnection(can_create_schema=True))
    with pytest.raises(work.WorkContextUnavailable, match="go_work_role_has_write_privileges"):
        work.official_context("obra 1093", connect=lambda *args, **kwargs: FakeReadOnlyConnection(can_create_database=True))
    with pytest.raises(work.WorkContextUnavailable, match="go_work_too_many_budgets"):
        work.official_context(
            " ".join(f"obra {n}" for n in range(1000, 1009)),
            connect=lambda *args, **kwargs: None,
        )


def test_readonly_adapter_never_scans_ledger_without_explicit_work(monkeypatch):
    monkeypatch.delenv("GO_WORK_READONLY_DSN", raising=False)
    assert work.official_context("Hola, ¿cómo estás?") is None
    with pytest.raises(work.WorkContextUnavailable, match="go_work_readonly_not_configured"):
        work.official_context("¿Qué pasó en la obra 1093?")


class FakeBackend:
    def __init__(self):
        self.messages = []

    def answer(self, messages, images=None):
        self.messages.append(messages)
        return "Encontré una medición de ocho horas, sin realizar modificaciones."


def _prepare_chat(monkeypatch, tmp_path):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "work.db")))
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")
    assert app_module.store.create_user("worker", "test-only-password")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="none"),
    )
    monkeypatch.setattr("iachat.tool_planner.is_file_action_candidate", lambda _: False)
    monkeypatch.setattr("iachat.auto_memory.learn", lambda *args: None)
    backend = FakeBackend()
    monkeypatch.setattr(app_module, "get_backend", lambda: backend)
    return backend


def test_work_chat_includes_official_data_as_untrusted_tool_evidence(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda text, **kwargs: "official-data-for-1093")
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Qué pasó en la obra 1093?"})
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    messages = backend.messages[0]
    assert any(m["role"] == "user" and "official-data-for-1093" in m["content"] for m in messages)
    assert all("official-data-for-1093" not in m["content"] for m in messages if m["role"] == "system")
    assert messages[-1]["content"] == "¿Qué pasó en la obra 1093?"


def test_http_chat_uses_real_read_adapter_for_official_work_status(monkeypatch, tmp_path):
    """HTTP -> SQL adapter -> model context, without any external inference."""
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    original = work.official_context
    monkeypatch.setattr(
        work, "official_context",
        lambda message, **kwargs: original(message, history=kwargs.get("history"), connect=lambda *args, **kwargs: connection),
    )
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Cuál es el estado de obra 1093?"})
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    assert any(
        m["role"] == "user" and '"estado": "pendiente"' in m["content"]
        and '"presupuesto": "1093"' in m["content"]
        for m in backend.messages[0]
    )
    assert all(
        sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
        for sql, _ in connection.statements
    )


def test_general_work_question_injects_official_overview_not_model_guess(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda text, **kwargs: (
        'Datos oficiales G.O.: {"total_obras": 3}' if "obras" in text else None
    ))
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Cuántas obras hay?"})
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    assert any(
        m["role"] == "user" and '"total_obras": 3' in m["content"]
        for m in backend.messages[0]
    )


def test_work_chat_fails_closed_without_official_db_instead_of_guessing(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    def fail(_, **kwargs):
        raise work.WorkContextUnavailable("go_work_readonly_unavailable")
    monkeypatch.setattr(work, "official_context", fail)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Qué pasó en la obra 1093?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "go_work_readonly_unavailable"
    assert backend.messages == []
    # IAchat main persists the user turn before provider/database work. A
    # failed official lookup must preserve that pending turn, but never invent
    # an assistant answer or write an official work record.
    conversations = app_module.store.list_conversations("worker")
    assert len(conversations) == 1
    history = app_module.store.get(conversations[0]["id"], "worker")
    assert history == [{"role": "user", "content": "¿Qué pasó en la obra 1093?"}]


def test_followup_reuses_only_last_unambiguous_operator_work(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    history = [
        {"role": "user", "content": "¿Qué pasó en obra 1093?"},
        {"role": "assistant", "content": "La obra 1190 también existe."},
    ]
    result = work.official_context(
        "¿Y qué se registró en esa obra?", history=history,
        connect=lambda *args, **kwargs: connection,
    )
    assert '"presupuesto": "1093"' in result
    assert '"presupuesto": "1190"' not in result
    assert any(params == ("1093",) for sql, params in connection.statements
               if sql.startswith("SELECT id,direccion,estado FROM obras"))


def test_followup_after_comparison_requires_clarification_without_sql(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    history = [
        {"role": "user", "content": "Compará obra 1093 con obra 1190"},
        {"role": "assistant", "content": "Dos obras diferentes."},
    ]
    with pytest.raises(work.WorkContextUnavailable, match="go_work_ambiguous_budget"):
        work.official_context(
            "¿Y qué pasó en esa obra?", history=history,
            connect=lambda *args, **kwargs: connection,
        )
    assert connection.statements == []


def test_followup_without_clear_reference_does_not_query_or_guess(monkeypatch):
    monkeypatch.delenv("GO_WORK_READONLY_DSN", raising=False)
    history = [{"role": "user", "content": "obra 1093"}]
    assert work.official_context("¿Qué hora es?", history=history) is None


def test_unresolved_work_reference_does_not_infer_from_assistant(monkeypatch):
    """A vague work follow-up must not guess a budget from assistant output."""
    monkeypatch.delenv("GO_WORK_READONLY_DSN", raising=False)
    history = [{"role": "assistant", "content": "La obra 1093 existe."}]
    with pytest.raises(work.WorkContextUnavailable, match="go_work_missing_budget"):
        work.official_context("¿Qué pasó en esa obra?", history=history)
    with pytest.raises(work.WorkContextUnavailable, match="go_work_missing_budget"):
        work.official_context("¿Y ese presupuesto?", history=[])
    # A casual locative phrase is not by itself a work reference.
    assert work.official_context("¿Cómo estás ahí?", history=[]) is None


def test_bare_budget_only_resolves_pending_server_clarification(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    history = [
        {"role": "user", "content": "¿Qué pasó en esa obra?"},
        {"role": "assistant", "content": work.WORK_CLARIFICATION_PROMPT},
    ]
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "1093", history=history, connect=lambda *args, **kwargs: connection,
    )
    assert '"presupuesto": "1093"' in result
    assert any(params == ("1093",) for sql, params in connection.statements
               if sql.startswith("SELECT id,direccion,estado FROM obras"))
    # An assistant's work number is never a source of work identity, and a
    # number outside a pending clarification must not trigger ledger reads.
    assert work.official_context("1093", history=[
        {"role": "assistant", "content": work.WORK_CLARIFICATION_PROMPT},
    ]) is None
    assert work.official_context("1093", history=[
        {"role": "user", "content": "¿Qué pasó en esa obra?"},
        {"role": "assistant", "content": "La obra 1190 existe."},
    ]) is None
    assert work.official_context("1093", history=[]) is None

    # A locative follow-up can be ambiguous too. A bare budget is accepted
    # only after the server itself asked which work, never from model output.
    locative_history = [
        {"role": "user", "content": "¿Y ahí?"},
        {"role": "assistant", "content": work.WORK_CLARIFICATION_PROMPT},
    ]
    assert '"presupuesto": "1190"' in work.official_context(
        "1190", history=locative_history,
        connect=lambda *args, **kwargs: FakeReadOnlyConnection(),
    )
    assert work.official_context("1190", history=[
        {"role": "user", "content": "¿Y ahí?"},
        {"role": "assistant", "content": "La obra 1190 existe."},
    ]) is None


def test_http_clarification_then_official_work_query(monkeypatch, tmp_path):
    """Clarify first, then use official evidence in the same labor conversation."""
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    original = work.official_context
    monkeypatch.setattr(
        work, "official_context",
        lambda message, **kwargs: original(
            message, history=kwargs.get("history"),
            connect=lambda *args, **kwargs: connection,
        ),
    )
    with TestClient(app_module.app, base_url="https://go.test") as client:
        first = client.post("/api/chat", json={"text": "¿Qué pasó en esa obra?"})
        assert first.status_code == 200, first.text
        assert "¿A qué obra te referís?" in first.json()["answer"]
        assert backend.messages == []
        assert connection.statements == []
        second = client.post("/api/chat", json={
            "conversation_id": first.json()["conversation_id"],
            "text": "Me refiero a la obra 1093",
        })
    assert second.status_code == 200, second.text
    assert len(second.json()["history"]) == 4
    assert len(backend.messages) == 1
    assert any(
        '"presupuesto": "1093"' in item["content"]
        for item in backend.messages[0] if item["role"] == "user"
    )
    assert len(app_module.store.list_conversations("worker")) == 1


def test_work_ledger_query_never_triggers_public_web_lookup(monkeypatch, tmp_path):
    """Official work evidence must not leak into IAchat's automatic web search."""
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(
        work, "official_context",
        lambda message, **kwargs: 'Datos oficiales G.O.: {"presupuesto":"1093"}',
    )
    def forbidden_web_plan(*args, **kwargs):
        raise AssertionError("labor ledger context must not trigger public web search")
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic", forbidden_web_plan,
    )
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={
            "text": "¿Qué pasó en la obra 1093?",
        })
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    assert any(
        "presupuesto" in item["content"]
        for item in backend.messages[0] if item["role"] == "user"
    )


def test_go_general_question_keeps_shared_web_planner(monkeypatch, tmp_path):
    """Do not disable IAchat's existing web-search functionality in G.O."""
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda message, **kwargs: None)
    planned = []
    def plan(message, history, selected_backend):
        planned.append(message)
        return SimpleNamespace(action="none")
    monkeypatch.setattr("iachat.web_planner.plan_web_lookup_semantic", plan)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={
            "text": "¿Cuándo es el próximo eclipse?",
        })
    assert response.status_code == 200, response.text
    assert planned == ["¿Cuándo es el próximo eclipse?"]
    assert len(backend.messages) == 1


def test_public_web_policy_requires_explicit_operator_request_for_work():
    assert not work.public_web_allowed(
        "¿Qué novedades hay en Montevideo y Corrientes?",
        work_profile=True, official_evidence=False,
    )
    assert not work.public_web_allowed(
        "Registrá lo que hizo la cuadrilla hoy en Uriburu",
        work_profile=True, official_evidence=False,
    )
    assert work.public_web_allowed(
        "Buscá en internet las últimas noticias de River",
        work_profile=True, official_evidence=False,
    )
    assert work.public_web_allowed(
        "¿Cuándo es el próximo eclipse?",
        work_profile=True, official_evidence=False,
    )
    assert not work.public_web_allowed(
        "¿Y qué pasó hoy?",
        work_profile=True, official_evidence=False,
        history=[{"role": "user", "content": "¿Cómo va la obra 1093?"}],
    )
    assert not work.public_web_allowed(
        "Buscá en internet información sobre obra 1093",
        work_profile=True, official_evidence=True,
    )
    assert work.public_web_allowed(
        "¿Qué novedades hay en Montevideo?",
        work_profile=False, official_evidence=False,
    )



def test_multiword_labor_addresses_never_enter_automatic_public_web():
    # These are real-world address shapes used in the work chat. No budget is
    # needed to protect them from a public search planner.
    for message in (
        "¿Qué pasó en Av. Rivadavia y Rodríguez Peña?",
        "¿Hay novedades en Combate de los Pozos 1590?",
        "¿Qué hay en Avenida Santa Fe 2380?",
        "¿Qué pasó en Montevideo y Corrientes?",
        "Registrá algo en Av. Rivadavia 1234",
    ):
        assert not work.public_web_allowed(
            message, work_profile=True, official_evidence=False,
        ), message
    # A public/general question still uses IAchat's shared search behavior.
    assert work.public_web_allowed(
        "¿Cuándo es el próximo eclipse?",
        work_profile=True, official_evidence=False,
    )
    # Personal IAchat must never inherit this labor-only restriction.
    assert work.public_web_allowed(
        "¿Qué pasó en Av. Rivadavia y Rodríguez Peña?",
        work_profile=False, official_evidence=False,
    )


def test_old_labor_context_never_reopens_automatic_public_search():
    history = [{"role": "user", "content": "¿Qué pasó en obra 1093?"}]
    history.extend([
        {"role": "assistant", "content": "Entendido."},
        {"role": "user", "content": "Gracias."},
    ] * 15)
    assert not work.public_web_allowed(
        "¿Y mañana?", work_profile=True, official_evidence=False,
        history=history,
    )


def test_explicit_public_search_never_sends_labor_history_to_planner(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda *args, **kwargs: None)
    app_module.store.put(
        "labor-history", [
            {"role": "user", "content": "¿Qué pasó en la obra 1093?"},
            {"role": "assistant", "content": "Pendiente de consultar."},
        ], "worker", "",
    )
    observed = []
    def plan(message, history, selected_backend):
        observed.append((message, history))
        return SimpleNamespace(action="none")
    monkeypatch.setattr("iachat.web_planner.plan_web_lookup_semantic", plan)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={
            "conversation_id": "labor-history",
            "text": "Buscá en internet las últimas noticias de River",
        })
    assert response.status_code == 200, response.text
    assert observed == [("Buscá en internet las últimas noticias de River", [])]
    assert len(backend.messages) == 1


def test_unrecognized_work_address_does_not_reach_public_web_planner(monkeypatch, tmp_path):
    """No budget/SQL match must not imply permission to search public web."""
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda *args, **kwargs: None)
    def forbidden_planner(*args, **kwargs):
        raise AssertionError("Labor details must not reach the public web planner")
    monkeypatch.setattr("iachat.web_planner.plan_web_lookup_semantic", forbidden_planner)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={
            "text": "¿Qué pasó hoy en Montevideo y Corrientes?"
        })
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1


def test_explicit_public_web_request_remains_available_in_work_profile(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda *args, **kwargs: None)
    planned = []
    def plan(message, *args, **kwargs):
        planned.append(message)
        return SimpleNamespace(action="none")
    monkeypatch.setattr("iachat.web_planner.plan_web_lookup_semantic", plan)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={
            "text": "Buscá en internet las últimas noticias de River"
        })
    assert response.status_code == 200, response.text
    assert planned == ["Buscá en internet las últimas noticias de River"]
    assert len(backend.messages) == 1


def test_address_without_budget_reads_existing_work_with_parameterized_sql(monkeypatch):
    """An address is evidence to query, not permission to guess a budget."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "¿Qué se registró en Alsina 354?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"presupuesto": "1190"' in result
    assert '"horas": 6' in result
    assert any(
        sql.startswith("SELECT presupuesto,direccion,estado FROM obras WHERE direccion ILIKE")
        and params == ("%Alsina 354%",)
        and "LIMIT 9" in sql
        for sql, params in connection.statements
    )
    assert all(
        sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
        for sql, _ in connection.statements
    )


def test_ambiguous_or_unknown_address_never_selects_an_arbitrary_work(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    ambiguous = work.official_context(
        "¿Qué pasó en Rivadavia y Rodríguez Peña?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "direccion_ambigua"' in ambiguous
    assert '"requiere_aclaracion": true' in ambiguous
    assert '"presupuesto": "1093"' in ambiguous
    assert '"presupuesto": "1993"' in ambiguous
    assert not any(sql.startswith("SELECT id,direccion,estado FROM obras")
                   for sql, _ in connection.statements)

    connection = FakeReadOnlyConnection()
    missing = work.official_context(
        "Montevideo 1058",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "direccion_sin_coincidencias"' in missing
    assert '"obras_coincidentes": []' in missing
    assert not any(sql.startswith("SELECT id,direccion,estado FROM obras")
                   for sql, _ in connection.statements)
    # 'de' is part of the street name, not the start of the address.
    connection = FakeReadOnlyConnection()
    work.official_context(
        "Combate de los Pozos 1590",
        connect=lambda *args, **kwargs: connection,
    )
    assert any(
        sql.startswith("SELECT presupuesto,direccion,estado FROM obras WHERE direccion ILIKE")
        and params == ("%Combate de los Pozos 1590%",)
        for sql, params in connection.statements
    )


def test_bare_addresses_and_budget_aliases_do_not_reach_public_search():
    for text in (
        "Montevideo 1058", "Combate de los Pozos 1590",
        "Av. Rivadavia y Rodríguez Peña", "P 1093", "Pto 1190",
    ):
        assert not work.public_web_allowed(
            text, work_profile=True, official_evidence=False,
        ), text
    assert work.public_web_allowed(
        "¿Cuándo es la próxima carrera de F1?",
        work_profile=True, official_evidence=False,
    )
    assert work.public_web_allowed(
        "Montevideo 1058", work_profile=False, official_evidence=False,
    )


def test_http_address_only_work_query_uses_official_evidence_without_public_web(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    original = work.official_context
    monkeypatch.setattr(
        work, "official_context",
        lambda message, **kwargs: original(
            message, history=kwargs.get("history"),
            connect=lambda *args, **kwargs: connection,
        ),
    )
    def forbidden_web(*args, **kwargs):
        raise AssertionError("Address-only labor query must not enter public web planner")
    monkeypatch.setattr("iachat.web_planner.plan_web_lookup_semantic", forbidden_web)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Qué pasó en Alsina 354?"})
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    assert any(
        item["role"] == "user" and '"presupuesto": "1190"' in item["content"]
        and '"direccion": "Alsina 354"' in item["content"]
        for item in backend.messages[0]
    )


def test_address_followup_reads_latest_operator_address_not_stale_budget(monkeypatch):
    """An address in a newer user turn supersedes an older numbered work."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    history = [
        {"role": "user", "content": "¿Qué pasó en la obra 1093?"},
        {"role": "assistant", "content": "Respuesta previa."},
        {"role": "user", "content": "¿Qué pasó en Alsina 354?"},
        {"role": "assistant", "content": "Respuesta basada en el registro."},
    ]
    connection = FakeReadOnlyConnection()
    result = work.official_context(
        "¿Y qué hicieron ahí?", history=history,
        connect=lambda *args, **kwargs: connection,
    )
    assert '"presupuesto": "1190"' in result
    assert '"horas": 6' in result
    assert '"presupuesto": "1093"' not in result
    assert any(params == ("%Alsina 354%",) for sql, params in connection.statements
               if "WHERE direccion ILIKE" in sql)
    assert not any(params == ("1093",) for sql, params in connection.statements
                   if sql.startswith("SELECT id,direccion,estado FROM obras"))


def test_multiple_addresses_require_clarification_without_database_query(monkeypatch):
    """Never silently select the first of two address-only work references."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    with pytest.raises(work.WorkContextUnavailable, match="go_work_missing_budget"):
        work.official_context(
            "¿Qué pasó en Alsina 354 y en Suipacha 671?",
            connect=lambda *args, **kwargs: connection,
        )
    assert connection.statements == []
    history = [
        {"role": "user", "content": "¿Qué pasó en Alsina 354 y en Suipacha 671?"},
        {"role": "assistant", "content": "Indicá cuál obra."},
    ]
    with pytest.raises(work.WorkContextUnavailable, match="go_work_missing_budget"):
        work.official_context(
            "¿Y qué hicieron ahí?", history=history,
            connect=lambda *args, **kwargs: connection,
        )
    assert connection.statements == []


def test_address_followup_never_trusts_assistant_generated_location(monkeypatch):
    monkeypatch.delenv("GO_WORK_READONLY_DSN", raising=False)
    assert work.official_context(
        "¿Qué pasó ahí?",
        history=[{"role": "assistant", "content": "Obra en Alsina 354."}],
    ) is None


def test_address_number_prefix_cannot_select_a_different_work(monkeypatch):
    """Alsina 354 must not resolve to Alsina 3540 via SQL ILIKE."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")

    class PrefixOnly(FakeReadOnlyConnection):
        def execute(self, sql, params=None):
            if sql.startswith("SELECT presupuesto,direccion,estado FROM obras WHERE direccion ILIKE"):
                return Result(many=[("1999", "Alsina 3540", "pendiente")])
            return super().execute(sql, params)

    connection = PrefixOnly()
    result = work.official_context(
        "¿Qué pasó en Alsina 354?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "direccion_sin_coincidencias"' in result
    assert '"presupuesto": "1999"' not in result
    assert not any(sql.startswith("SELECT id,direccion,estado FROM obras")
                   for sql, _ in connection.statements)


def test_full_address_candidate_page_never_claims_unique_work(monkeypatch):
    """Nine substring matches may hide another exact work beyond LIMIT 9."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")

    class FullPage(FakeReadOnlyConnection):
        def execute(self, sql, params=None):
            if sql.startswith("SELECT presupuesto,direccion,estado FROM obras WHERE direccion ILIKE"):
                return Result(many=[
                    (str(2000 + i), f"Alsina 354{i}", "pendiente") for i in range(8)
                ] + [("1190", "Alsina 354", "en_ejecucion")])
            return super().execute(sql, params)

    connection = FullPage()
    result = work.official_context(
        "¿Qué pasó en Alsina 354?",
        connect=lambda *args, **kwargs: connection,
    )
    assert '"consulta": "direccion_busqueda_limitada"' in result
    assert '"requiere_aclaracion": true' in result
    assert '"muestra_limitada": true' in result
    assert not any(sql.startswith("SELECT id,direccion,estado FROM obras")
                   for sql, _ in connection.statements)


def test_explicit_budget_and_address_must_identify_same_official_work(monkeypatch):
    """Do not silently prefer the budget over a conflicting address."""
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    valid = FakeReadOnlyConnection()
    evidence = work.official_context(
        "¿Qué pasó en obra 1190 en Alsina 354?",
        connect=lambda *args, **kwargs: valid,
    )
    assert '"presupuesto": "1190"' in evidence
    assert '"horas": 6' in evidence
    assert '"consulta": "direccion_presupuesto_incompatibles"' not in evidence

    conflict = FakeReadOnlyConnection()
    evidence = work.official_context(
        "Registrá 3 horas en obra 1093 en Alsina 354",
        connect=lambda *args, **kwargs: conflict,
    )
    assert '"consulta": "direccion_presupuesto_incompatibles"' in evidence
    assert '"presupuesto_indicado": "1093"' in evidence
    assert '"direccion_indicada": "Alsina 354"' in evidence
    assert '"requiere_aclaracion": true' in evidence
    assert '"registros"' not in evidence
    # The official work may be read to check its address, but its events must
    # not become trusted evidence when the operator's references conflict.
    assert not any("FROM go_record_events e" in sql for sql, _ in conflict.statements)


def test_multiple_mixed_references_require_clarification_before_sql(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    with pytest.raises(work.WorkContextUnavailable, match="go_work_ambiguous_budget"):
        work.official_context(
            "Compará obra 1093 y obra 1190 en Alsina 354",
            connect=lambda *args, **kwargs: connection,
        )
    assert connection.statements == []
    # Ordinary explicit budget phrases are not mistaken for addresses.
    assert work._address_references("¿Qué pasó en obra 1093?") == []
    assert work._address_references("¿Qué pasó en presupuesto 1093?") == []
    assert work._address_references("¿Qué se registró en la obra 1093?") == []
    assert work._address_references("¿Qué se registró en el presupuesto 1093?") == []


def test_http_ambiguous_comparison_followup_can_be_clarified_by_budget(monkeypatch, tmp_path):
    """After comparing works, an ambiguous follow-up asks; a bare reply resolves it.

    No model is called for the ambiguous turn and no work is guessed. This
    uses the real HTTP chat route and a bounded read-only PostgreSQL adapter.
    """
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    original = work.official_context
    monkeypatch.setattr(
        work, "official_context",
        lambda message, **kwargs: original(
            message, history=kwargs.get("history"),
            connect=lambda *args, **kwargs: connection,
        ),
    )
    with TestClient(app_module.app, base_url="https://go.test") as client:
        comparison = client.post("/api/chat", json={
            "text": "Compará obra 1093 con obra 1190",
        })
        assert comparison.status_code == 200, comparison.text
        conversation_id = comparison.json()["conversation_id"]
        assert len(backend.messages) == 1

        clarification = client.post("/api/chat", json={
            "conversation_id": conversation_id,
            "text": "¿Y ahí?",
        })
        assert clarification.status_code == 200, clarification.text
        assert clarification.json()["answer"] == work.WORK_CLARIFICATION_PROMPT
        assert len(backend.messages) == 1, "ambiguous work must not reach a model"

        resolved = client.post("/api/chat", json={
            "conversation_id": conversation_id, "text": "1190",
        })
        assert resolved.status_code == 200, resolved.text
        assert len(backend.messages) == 2
        latest_official = [
            item["content"] for item in backend.messages[-1]
            if item["role"] == "user"
            and item["content"].startswith("[DATOS OFICIALES DE HERRAMIENTA")
        ]
        assert len(latest_official) == 1
        assert '"presupuesto": "1190"' in latest_official[0]
        assert '"presupuesto": "1093"' not in latest_official[0]
        assert len(resolved.json()["history"]) == 6


def test_work_budget_in_long_natural_update_is_not_an_address(monkeypatch):
    """An operator can mention a work, date and details in one chat turn.

    The street matcher must not turn "de juntas en obra 1093" into a
    contradictory address. Genuine mixed budget/street references remain
    checked separately against PostgreSQL.
    """
    message = (
        "Registrá control de juntas en obra 1093, fecha 2026-11-01, "
        "revisar, 4 metros"
    )
    assert work._address_references(message) == []
    assert work._address_references(
        "Registrá horas de personal en la obra 1093"
    ) == []
    assert work._address_references(
        "Registrá horas en obra 1093 en Alsina 354"
    ) == ["Alsina 354"]
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    connection = FakeReadOnlyConnection()
    evidence = work.official_context(
        message, connect=lambda *args, **kwargs: connection,
    )
    assert '"presupuesto": "1093"' in evidence
    assert '"encontrada": true' in evidence
    assert '"consulta": "direccion_presupuesto_incompatibles"' not in evidence
