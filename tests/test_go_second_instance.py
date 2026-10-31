"""Offline regressions for the same IAchat engine in a separate work instance.

These tests never connect to Oracle, Router, PostgreSQL or a provider account.
"""
from types import SimpleNamespace

import pytest

from fastapi.testclient import TestClient

import iachat.app as app_module
from iachat.store import ConversationStore
from iachat.file_workspace import FileWorkspace
from iachat.structured_data import StructuredStore


class FakeConversationalBackend:
    def __init__(self):
        self.messages = []

    def answer(self, messages, images=None):
        self.messages.append(messages)
        return "No guardé ninguna novedad oficial. Falta confirmación en PostgreSQL."


def test_go_profile_reuses_chat_without_automatic_sqlite_work_writes(monkeypatch, tmp_path):
    path = str(tmp_path / "work-instance.db")
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setattr(app_module, "store", ConversationStore(path))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(path))
    monkeypatch.setattr(app_module, "structured_store", StructuredStore(path))
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "worker")
    assert app_module.store.create_user("worker", "test-only-password")
    # A stored memory must never replace the trusted work-only safety policy.
    app_module.store.save_memory("test-memory", "Turno de mañana", "worker")
    backend = FakeConversationalBackend()
    monkeypatch.setattr(app_module, "get_backend", lambda: backend)
    monkeypatch.setattr(
        app_module, "handle_structured_chat",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("work profile must not write via SQLite structured collections")
        ),
    )
    monkeypatch.setattr(
        "iachat.web_planner.plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="none"),
    )
    monkeypatch.setattr("iachat.tool_planner.is_file_action_candidate", lambda _: False)
    monkeypatch.setattr("iachat.auto_memory.learn", lambda *args: None)
    # This test isolates the chat engine; PostgreSQL access is covered by
    # test_go_work_readonly.py and must never contact Oracle in CI.
    monkeypatch.setattr("iachat.go_work_context.official_context", lambda _: "datos oficiales simulados")

    with TestClient(app_module.app, base_url="https://go.test") as first:
        result = first.post("/api/chat", json={
            "text": "Registrá 8 horas ejecutadas para la obra 1190"
        })
        assert result.status_code == 200, result.text
        conversation_id = result.json()["conversation_id"]
        assert "No guardé ninguna novedad oficial" in result.json()["answer"]
        assert app_module.structured_store.collections("worker") == []
        assert any("Turno de mañana" in m["content"] for m in backend.messages[-1] if m["role"] == "system")
        assert any(
            "NO modifica registros oficiales" in m["content"]
            for m in backend.messages[-1] if m["role"] == "system"
        )
    # A second browser session reads the same isolated work-instance SQLite.
    with TestClient(app_module.app, base_url="https://go.test") as second:
        history = second.get("/api/conversations/" + conversation_id)
        assert history.status_code == 200
        assert len(history.json()["history"]) == 2


def test_personal_profile_keeps_existing_structured_data_route(monkeypatch, tmp_path):
    path = str(tmp_path / "personal-instance.db")
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.setattr(app_module, "store", ConversationStore(path))
    monkeypatch.setattr(app_module, "file_workspace", FileWorkspace(path))
    monkeypatch.setattr(app_module, "structured_store", StructuredStore(path))
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "personal")
    assert app_module.store.create_user("personal", "test-only-password")
    calls = []
    def existing_handler(*args):
        calls.append(args)
        return {"answer": "Ruta personal conservada."}
    monkeypatch.setattr(app_module, "handle_structured_chat", existing_handler)
    with TestClient(app_module.app, base_url="https://personal.test") as client:
        response = client.post("/api/chat", json={"text": "anotá un gasto"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Ruta personal conservada."
    assert len(calls) == 1


def test_two_sqlite_instances_do_not_share_users_memories_or_conversations(tmp_path):
    personal_path = tmp_path / "personal.db"
    work_path = tmp_path / "work.db"
    personal = ConversationStore(str(personal_path))
    work = ConversationStore(str(work_path))
    assert personal.create_user("alice", "test-only-password")
    assert work.create_user("alice", "another-test-password")
    personal.put("private-conversation", [{"role": "user", "content": "personal"}], "alice")
    personal.save_memory("memory-1", "private memory", "alice")
    assert work.get("private-conversation", "alice") is None
    assert work.list_memories("alice") == []
    assert work.verify_user("alice", "another-test-password")
    assert not work.verify_user("alice", "test-only-password")


def test_work_profile_requires_explicit_isolated_db_and_session_secret(tmp_path):
    validate = app_module._validate_work_instance_config
    # The personal instance retains its current configuration contract.
    validate("personal", "", "")
    with pytest.raises(RuntimeError, match="explicit_absolute_iachat_db"):
        validate("go-ute", "", "s" * 32)
    with pytest.raises(RuntimeError, match="explicit_absolute_iachat_db"):
        validate("go-ute", "iachat.db", "s" * 32)
    with pytest.raises(RuntimeError, match="dedicated_auth_secret"):
        validate("go-ute", str(tmp_path / "work.db"), "short")
    validate("go-ute", str(tmp_path / "work.db"), "s" * 32)


def test_work_google_login_requires_explicit_subject_approval(monkeypatch, tmp_path):
    """Google verification alone must never enroll an arbitrary labor user."""
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.delenv("IACHAT_GOOGLE_ALLOWED_SUBS", raising=False)
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "go-google.db")))
    monkeypatch.setattr(app_module.google_oidc, "complete", lambda *args: "google-sub-123")
    with TestClient(app_module.app, base_url="https://go.test") as client:
        denied = client.get("/auth/google/callback?code=test&state=test", follow_redirects=False)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "google_account_not_authorized"
        assert app_module.store.list_users() == []
        monkeypatch.setenv("IACHAT_GOOGLE_ALLOWED_SUBS", "another-sub, google-sub-123")
        allowed = client.get("/auth/google/callback?code=test&state=test", follow_redirects=False)
        assert allowed.status_code == 303
        assert len(app_module.store.list_users()) == 1


def test_personal_google_enrollment_policy_unchanged(monkeypatch):
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.delenv("IACHAT_GOOGLE_ALLOWED_SUBS", raising=False)
    assert app_module._work_google_subject_allowed("new-personal-google-sub")
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    assert not app_module._work_google_subject_allowed("new-personal-google-sub")
    monkeypatch.setenv("IACHAT_GOOGLE_ALLOWED_SUBS", "approved-sub")
    assert app_module._work_google_subject_allowed("approved-sub")
    assert not app_module._work_google_subject_allowed("other-sub")


def test_work_profile_rejects_password_login_and_legacy_admin_bootstrap(monkeypatch, tmp_path):
    """A Google subject allowlist must not be bypassed through local passwords."""
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("IACHAT_PASSWORD", "legacy-password-must-not-work")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "work-auth.db")))
    with TestClient(app_module.app, base_url="https://go.test") as client:
        denied = client.post("/auth/login", json={
            "username": "admin", "password": "legacy-password-must-not-work"
        })
        assert denied.status_code == 403
        assert denied.json()["detail"] == "go_google_only_authentication"
        assert app_module.store.get_user("admin") is None
        assert "iachat_session" not in denied.cookies


def test_work_profile_rejects_local_account_management(monkeypatch, tmp_path):
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "work-users.db")))
    assert app_module.store.create_user("admin", "existing-test-password", admin=True)
    monkeypatch.setattr(app_module, "_signed_user", lambda _: "admin")
    with TestClient(app_module.app, base_url="https://go.test") as client:
        new_user = client.post("/api/users", json={
            "username": "unauthorized", "password": "password123"
        })
        password_change = client.post("/api/account/password", json={
            "current_password": "existing-test-password",
            "new_password": "another-password123"
        })
    assert new_user.status_code == 403
    assert password_change.status_code == 403
    assert app_module.store.get_user("unauthorized") is None
    assert app_module.store.verify_user("admin", "existing-test-password")


def test_personal_password_login_remains_available(monkeypatch, tmp_path):
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "personal-test-secret-32-characters-minimum")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "personal-auth.db")))
    assert app_module.store.create_user("alice", "valid-test-password")
    with TestClient(app_module.app, base_url="https://personal.test") as client:
        result = client.post("/auth/login", json={
            "username": "alice", "password": "valid-test-password"
        })
    assert result.status_code == 200
    assert "iachat_session" in result.cookies


def test_session_signatures_are_profile_bound_even_if_secret_is_reused(monkeypatch, tmp_path):
    """Even an accidentally reused secret and username cannot replay cookies."""
    import hashlib
    import hmac
    import time

    monkeypatch.setenv("IACHAT_AUTH_SECRET", "accidentally-shared-test-secret-at-least-32-characters")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "both-profiles-test.db")))
    assert app_module.store.create_user("same-user", "test-only-password")
    expiry = str(int(time.time()) + 3600)

    def token_for_current_profile():
        payload = app_module._session_mac_payload("same-user", expiry)
        signature = hmac.new(
            os.environ["IACHAT_AUTH_SECRET"].encode(), payload, hashlib.sha256
        ).hexdigest()
        return "same-user." + expiry + "." + signature

    import os
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    personal_cookie = token_for_current_profile()
    assert app_module._signed_user(personal_cookie) == "same-user"

    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    assert app_module._signed_user(personal_cookie) is None
    work_cookie = token_for_current_profile()
    assert app_module._signed_user(work_cookie) == "same-user"

    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    assert app_module._signed_user(work_cookie) is None


def test_work_google_callback_issues_work_bound_cookie(monkeypatch, tmp_path):
    """A real work OIDC callback must sign the profile-specific session."""
    monkeypatch.setenv("IACHAT_PROFILE", "go-ute")
    monkeypatch.setenv("IACHAT_AUTH_SECRET", "isolated-work-test-secret-at-least-32-characters")
    monkeypatch.setenv("IACHAT_GOOGLE_ALLOWED_SUBS", "approved-google-sub")
    monkeypatch.setattr(app_module, "store", ConversationStore(str(tmp_path / "work-oidc.db")))
    monkeypatch.setattr(app_module.google_oidc, "complete", lambda *args: "approved-google-sub")
    with TestClient(app_module.app, base_url="https://go.test") as client:
        response = client.get("/auth/google/callback?code=test&state=test", follow_redirects=False)
    assert response.status_code == 303
    cookie = response.cookies.get("iachat_session", "")
    assert app_module._signed_user(cookie) is not None
    monkeypatch.setenv("IACHAT_PROFILE", "personal")
    assert app_module._signed_user(cookie) is None
