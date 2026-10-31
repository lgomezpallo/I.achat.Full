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
    def __init__(self, *, writable=False):
        self.statements = []
        self.writable = writable

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        if sql.startswith("SHOW transaction_read_only"):
            return Result(("on",))
        if "has_table_privilege" in sql:
            return Result((self.writable,))
        if sql == "SELECT COUNT(*) FROM obras":
            return Result((3,))
        if sql.startswith("SELECT estado,COUNT(*) FROM obras"):
            return Result(many=[("en_ejecucion", 2), ("pendiente", 1)])
        if sql.startswith("SELECT presupuesto,direccion,estado FROM obras"):
            return Result(many=[
                ("1093", "Rivadavia y Rodríguez Peña", "en_ejecucion"),
                ("1190", "Alsina 354", "en_ejecucion"),
                ("1192", "Suipacha 671", "pendiente"),
            ])
        if sql.startswith("SELECT id,direccion FROM obras"):
            assert params in (("1093",), ("1190",))
            if params == ("1190",):
                return Result(("work-1190", "Alsina 354"))
            return Result(("work-uuid", "Rivadavia y Rodríguez Peña"))
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
    scoped = [(sql, params) for sql, params in connection.statements
              if sql.startswith("SELECT id,direccion FROM obras")]
    assert len(scoped) == 2
    assert {params for _, params in scoped} == {("1093",), ("1190",)}
    assert all(sql.startswith(("SET TRANSACTION READ ONLY", "SHOW transaction_read_only", "SELECT"))
               for sql, _ in connection.statements)


def test_readonly_adapter_refuses_writer_account_and_unbounded_comparison(monkeypatch):
    monkeypatch.setenv("GO_WORK_READONLY_DSN", "test-only")
    with pytest.raises(work.WorkContextUnavailable, match="go_work_role_has_write_privileges"):
        work.official_context("obra 1093", connect=lambda *args, **kwargs: FakeReadOnlyConnection(writable=True))
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
    monkeypatch.setattr(work, "official_context", lambda text: "official-data-for-1093")
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Qué pasó en la obra 1093?"})
    assert response.status_code == 200, response.text
    assert len(backend.messages) == 1
    messages = backend.messages[0]
    assert any(m["role"] == "user" and "official-data-for-1093" in m["content"] for m in messages)
    assert all("official-data-for-1093" not in m["content"] for m in messages if m["role"] == "system")
    assert messages[-1]["content"] == "¿Qué pasó en la obra 1093?"


def test_general_work_question_injects_official_overview_not_model_guess(monkeypatch, tmp_path):
    backend = _prepare_chat(monkeypatch, tmp_path)
    monkeypatch.setattr(work, "official_context", lambda text: (
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
    def fail(_):
        raise work.WorkContextUnavailable("go_work_readonly_unavailable")
    monkeypatch.setattr(work, "official_context", fail)
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.post("/api/chat", json={"text": "¿Qué pasó en la obra 1093?"})
    assert response.status_code == 503
    assert response.json()["detail"] == "go_work_readonly_unavailable"
    assert backend.messages == []
    assert app_module.store.list_conversations("worker") == []
