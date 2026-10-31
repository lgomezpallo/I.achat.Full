"""Offline checks for the *live* memory acceptance probe.

The fake backend is used only in CI. The production E2E calls the configured
free provider over authenticated HTTP, and never reports these mocks as live.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from fastapi.testclient import TestClient

from iachat.store import ConversationStore
from runpy import run_path
from pathlib import Path
probe = run_path(str(Path(__file__).resolve().parent.parent / "scripts" / "live_memory_probe.py"))
run_live_memory_probe = probe["run_live_memory_probe"]
seed_memory_probe = probe["seed_memory_probe"]
transcript_digest = probe["transcript_digest"]


def test_live_probe_seed_requires_archived_middle(tmp_path):
    store = ConversationStore(str(tmp_path / "probe.sqlite3"))
    seed_memory_probe(store, "alice", "probe-1", "LUCERO1234ABCD")
    history = store.get("probe-1", "alice")
    assert len(history) == 480
    assert history[200]["content"].find("LUCERO1234ABCD") >= 0
    summary = store.get_summary("probe-1", "alice")
    assert summary["processed_count"] == 480
    assert all("LUCERO1234ABCD" not in item["quote"] for item in summary["items"])


def test_live_probe_uses_authenticated_http_and_actual_context(tmp_path, monkeypatch):
    import iachat.app as module
    import iachat.web_planner as web_planner

    monkeypatch.setenv("IACHAT_AUTH_SECRET", "isolated-ci-signing-key-only")
    store = ConversationStore(str(tmp_path / "http.sqlite3"))
    assert store.create_user("alice", "test-password-alice")
    assert store.create_user("bob", "test-password-bob")
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(
        web_planner, "plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="none", reason="offline", query=""),
    )

    class FakeBackend:
        def answer(self, messages, images=None):
            context = "\n".join(item["content"] for item in messages)
            match = re.search(r"LUCERO[0-9A-F]{8}", context)
            assert match, "evicted middle fact did not reach the model input"
            return __import__("json").dumps({"base_de_datos": "PostgreSQL", "motor_violeta": match.group(), "respaldo": "diario"})

    monkeypatch.setattr(module, "get_backend", lambda: FakeBackend())
    client = TestClient(module.app, base_url="https://testserver")
    login = client.post("/auth/login", json={
        "username": "alice", "password": "test-password-alice",
    })
    assert login.status_code == 200
    assert run_live_memory_probe(
        client, store, "alice", "bob",
        lambda session, path, **kwargs: session.post(path, **kwargs),
    )


def test_live_probe_rejects_model_that_does_not_recall(tmp_path, monkeypatch):
    import iachat.app as module
    import iachat.web_planner as web_planner

    monkeypatch.setenv("IACHAT_AUTH_SECRET", "isolated-ci-signing-key-only")
    store = ConversationStore(str(tmp_path / "failure.sqlite3"))
    assert store.create_user("alice", "test-password-alice")
    monkeypatch.setattr(module, "store", store)
    monkeypatch.setattr(
        web_planner, "plan_web_lookup_semantic",
        lambda *args, **kwargs: SimpleNamespace(action="none", reason="offline", query=""),
    )

    class ForgetfulBackend:
        def answer(self, messages, images=None):
            return "No tengo información suficiente."

    monkeypatch.setattr(module, "get_backend", lambda: ForgetfulBackend())
    client = TestClient(module.app, base_url="https://testserver")
    assert client.post("/auth/login", json={
        "username": "alice", "password": "test-password-alice",
    }).status_code == 200
    assert not run_live_memory_probe(
        client, store, "alice", "bob",
        lambda session, path, **kwargs: session.post(path, **kwargs),
    )


def test_live_production_probe_detects_silent_middle_or_metadata_corruption():
    messages = [
        {"role": "user", "content": "inicio", "attachments": [{"name": "plano.pdf"}]},
        {"role": "assistant", "content": "respuesta", "model": "free"},
        {"role": "user", "content": "final"},
    ]
    baseline = transcript_digest(messages, 3)
    assert baseline is not None
    import copy
    changed = copy.deepcopy(messages)
    changed[1]["content"] = "alterado"
    assert transcript_digest(changed, 3) != baseline
    changed = copy.deepcopy(messages)
    changed[0]["attachments"][0]["name"] = "otro.pdf"
    assert transcript_digest(changed, 3) != baseline
    assert transcript_digest(messages[:2], 3) is None
