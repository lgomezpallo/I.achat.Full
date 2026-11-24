"""Guardrails for the Oracle deployment workflow (no cloud access needed)."""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "deploy-oracle.yml"
)


def test_oracle_deploy_requires_successful_main_ci_or_manual_dispatch():
    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "  workflow_dispatch:" in triggers
    assert "  workflow_run:" in triggers
    assert 'workflows: ["IAchat CI"]' in triggers
    assert "types: [completed]" in triggers
    for event in ("  push:", "  pull_request:", "  schedule:"):
        assert event not in triggers


def test_oracle_deploy_is_gated_to_main_success_and_explicit_environment():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in text
    assert "github.event.workflow_run.event == 'push'" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "environment: oracle-production" in text
    assert "github.event.workflow_run.head_sha || github.sha" in text
    assert "persist-credentials: false" in text
    assert "python -m pytest -q" in text


def test_postdeploy_checks_public_readiness_without_exposing_router_status():
    """An unauthenticated postdeploy probe must never require private /api access."""
    deploy = Path(__file__).resolve().parents[1] / "scripts" / "deploy_oracle.sh"
    script = deploy.read_text(encoding="utf-8")
    assert 'code, status = probe("/ready")' in script
    assert 'status.get("mode") == "router"' in script
    assert 'status.get("status") == "ready"' in script
    assert 'code, _ = probe("/api/router/status")' in script
    assert 'code, _ = probe("/api/conversations")' in script
    assert script.count('assert code == 401') >= 2
    assert 'code, status = probe("/api/router/status")' not in script


def test_deploy_selects_router_backend_without_direct_provider_keys():
    """IAchat must receive Router credentials, never provider API keys."""
    deploy = Path(__file__).resolve().parents[1] / "scripts" / "deploy_oracle.sh"
    script = deploy.read_text(encoding="utf-8")
    assert "Environment=IACHAT_BACKEND=router" in script
    assert "Environment=IACHAT_BACKEND=integrated" not in script
    assert "/etc/router-providers.env" not in script
    assert "/etc/iachat/router.env" in script
    assert "router_url_not_loopback" in script
    assert "http://127.0.0.1:8010/health" in script


def test_postdeploy_endpoint_contract_with_router_backend(monkeypatch):
    """Reproduce the release preflight offline, without credentials or inference."""
    from fastapi.testclient import TestClient
    from iachat import app as app_module

    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.setenv("ROUTER_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ROUTER_TOKEN", "offline-test-token")
    monkeypatch.setattr(app_module, "_signed_user", lambda cookie: None)
    client = TestClient(app_module.app, base_url="https://testserver")

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["mode"] == "router"
    assert ready.json()["status"] == "ready"
    assert client.get("/api/router/status").status_code == 401
    assert client.get("/api/conversations").status_code == 401
