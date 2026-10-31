"""The shared chat never commits a work proposal without scoped approval."""
from __future__ import annotations

from types import SimpleNamespace
import uuid
import pytest

from iachat import go_work_actions as actions


def _interpret(raw, message, *, attachments=False):
    return actions.interpret_model_answer(
        raw, message, actor="g_test_user", conversation_id="ci-conversation",
        attachments=attachments,
    )


def _decide(message, history):
    return actions.decide_in_conversation(
        message, history, actor="g_test_user", conversation_id="ci-conversation",
    )


def _work(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("GO_WORK_WRITE_ENABLED", "1")
    monkeypatch.setenv("GO_DATABASE_URL", "postgresql://test-only")
    assert actions.enabled()


def test_personal_profile_never_interprets_or_decides(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.setenv("GO_WORK_WRITE_ENABLED", "1")
    assert actions.instruction() is None
    raw = '{"go_intent":"v1","intent":"record"}'
    assert _interpret(raw, "Registrá") == (raw, None)
    assert _decide("Confirmo propuesta " + str(uuid.uuid4()), []) is None


def test_work_gate_off_by_default(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.delenv("GO_WORK_WRITE_ENABLED", raising=False)
    assert actions.instruction() is None
    assert not actions.enabled()


def test_strict_json_only_and_document_never_stage(monkeypatch):
    _work(monkeypatch)
    assert _interpret("texto normal", "novedad") == ("texto normal", None)
    answer, ref = _interpret(
        '{"go_intent":"v1","intent":"record","record_type":"medicion"}',
        "Registrá medición", attachments=True,
    )
    assert ref is None and "no modifiqué" in answer


def test_proposal_uses_existing_ledger_and_requires_same_conversation(monkeypatch):
    _work(monkeypatch)
    proposal = str(uuid.uuid4())
    decisions = []
    stages = []
    class InvalidProposal(ValueError):
        pass
    ledger = SimpleNamespace(
        InvalidProposal=InvalidProposal,
        stage=lambda data, text, **kwargs: (stages.append((data, text, kwargs)) or
                                  {"phase": "flexible_pending", "proposal_id": proposal, "reply": "Pendiente"}),
        decision_from_message=lambda text: (proposal, True),
        decide=lambda ref, approved, **kwargs: (decisions.append((ref, approved, kwargs)) or
                                      {"reply": "Confirmada"}),
    )
    monkeypatch.setattr(actions, "_ledger", lambda: ledger)
    raw = '{"go_intent":"v1","intent":"record","record_type":"medicion","budget":"1093","values":{"horas":3}}'
    answer, ref = _interpret(raw, "Registrá 3 horas para obra 1093")
    assert (answer, ref) == ("Pendiente", proposal)
    assert len(stages) == 1 and decisions == []
    command = "Confirmo propuesta " + proposal
    assert "no está pendiente" in _decide(command, [])
    assert decisions == []
    other_history = [{"role": "assistant", "go_proposal_id": str(uuid.uuid4())}]
    assert "no está pendiente" in _decide(command, other_history)
    assert decisions == []
    own_history = [{"role": "user", "content": "registrá"},
                   {"role": "assistant", "content": answer, "go_proposal_id": proposal}]
    assert _decide(command, own_history) == "Confirmada"
    assert decisions == [(proposal, True, {"actor": "g_test_user", "conversation_id": "ci-conversation"})]


def test_invalid_model_proposal_does_not_commit(monkeypatch):
    _work(monkeypatch)
    class InvalidProposal(ValueError):
        pass
    def stage(*args):
        raise InvalidProposal("Obra ambigua")
    monkeypatch.setattr(actions, "_ledger", lambda: SimpleNamespace(
        InvalidProposal=InvalidProposal, stage=stage,
    ))
    reply, ref = _interpret(
        '{"go_intent":"v1","intent":"record","record_type":"medicion","budget":"1093","values":{"horas":3}}',
        "Registrá en obra 1190",
    )
    assert ref is None and "Obra ambigua" in reply


def test_short_confirmation_scoped_to_immediate_pending_assistant(monkeypatch):
    _work(monkeypatch)
    proposal = str(uuid.uuid4())
    decisions = []
    ledger = SimpleNamespace(
        decide=lambda ref, approved: (decisions.append((ref, approved)) or
                                      {"reply": "Confirmada" if approved else "Descartada"}),
    )
    monkeypatch.setattr(actions, "_ledger", lambda: ledger)
    own = [{"role": "user", "content": "Registrá una novedad"},
           {"role": "assistant", "content": "Propuesta pendiente", "go_proposal_id": proposal}]
    assert _decide("dale", own) == "Confirmada"
    assert _decide("sí", own) == "Confirmada"
    assert _decide("descartala", own) is None
    assert _decide("descartá", own) == "Descartada"
    assert _decide("no", own) == "Descartada"
    assert decisions == [(proposal, approved, {"actor": "g_test_user", "conversation_id": "ci-conversation"}) for approved in (True, True, False, False)]


def test_short_confirmation_never_uses_another_conversation_or_stale_turn(monkeypatch):
    _work(monkeypatch)
    proposal = str(uuid.uuid4())
    monkeypatch.setattr(actions, "_ledger", lambda: (_ for _ in ()).throw(
        AssertionError("No database access without immediate pending proposal")
    ))
    assert _decide("dale", []) is None
    assert _decide("ok", [{"role": "assistant", "content": "Normal"}]) is None
    assert _decide("sí", [
        {"role": "assistant", "content": "Pending", "go_proposal_id": proposal},
        {"role": "user", "content": "Otra consulta"},
        {"role": "assistant", "content": "Respuesta normal"},
    ]) is None
    assert _decide("no", [
        {"role": "assistant", "content": "Pending", "go_proposal_id": "not-a-uuid"}
    ]) is None
    assert _decide("dale, cambiá también la obra", [
        {"role": "assistant", "content": "Pending", "go_proposal_id": proposal}
    ]) is None


def test_postgres_failure_in_stage_returns_controlled_error(monkeypatch):
    """A broken ledger must not produce a false 'pending' confirmation."""
    _work(monkeypatch)

    class InvalidProposal(ValueError):
        pass

    def broken_stage(*args):
        raise OSError("private-dsn-and-database-details")

    monkeypatch.setattr(actions, "_ledger", lambda: SimpleNamespace(
        InvalidProposal=InvalidProposal, stage=broken_stage,
    ))
    raw = '{"go_intent":"v1","intent":"record","record_type":"medicion","budget":"1093","values":{"horas":3}}'
    with pytest.raises(RuntimeError, match="^go_work_approval_unavailable$") as error:
        _interpret(raw, "Registrá en obra 1093")
    assert "private-dsn" not in str(error.value)


@pytest.mark.parametrize("message", ["dale", "Confirmo propuesta {id}"])
def test_postgres_failure_in_decision_returns_controlled_error(monkeypatch, message):
    """Both natural and explicit approvals fail closed on database errors."""
    _work(monkeypatch)
    proposal = str(uuid.uuid4())

    def broken_decide(*args):
        raise OSError("private-dsn-and-database-details")

    monkeypatch.setattr(actions, "_ledger", lambda: SimpleNamespace(
        decide=broken_decide,
        decision_from_message=lambda _: (proposal, True),
    ))
    history = [{"role": "assistant", "content": "Pendiente", "go_proposal_id": proposal}]
    with pytest.raises(RuntimeError, match="^go_work_approval_unavailable$") as error:
        _decide(message.format(id=proposal), history)
    assert "private-dsn" not in str(error.value)
