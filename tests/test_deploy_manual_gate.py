"""Guardrails for the Oracle deployment workflow (no cloud access needed)."""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "deploy-oracle.yml"
)


def test_oracle_deploy_is_manual_only():
    """Merging to main must never deploy production without the Router audit."""
    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "  workflow_dispatch:" in triggers
    for event in ("  push:", "  pull_request:", "  schedule:", "  workflow_run:"):
        assert event not in triggers
    assert "workflow_run" not in text


def test_oracle_deploy_is_gated_to_main_and_explicit_environment():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in text
    assert "environment: oracle-production" in text
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


def test_deploy_provisions_session_signing_key_without_printing_it():
    """No login can succeed without IACHAT_AUTH_SECRET; it is created once."""
    script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_oracle.sh").read_text(encoding="utf-8")
    assert '/etc/iachat/auth.env' in script
    assert 'IACHAT_AUTH_SECRET=%s' in script
    assert 'EnvironmentFile=/etc/iachat/auth.env' in script
    assert 'AUTH_SECRET_FILE' in script
    for leak in ('echo "$IACHAT_AUTH_SECRET', "print(cfg", 'print(secret'):
        assert leak not in script


def test_deploy_uses_the_unit_port_and_the_real_router_env_path():
    """The VM runs uvicorn on 8001 and keeps Router credentials in /etc/iachat-router.env."""
    script = (Path(__file__).resolve().parents[1] / "scripts" / "deploy_oracle.sh").read_text(encoding="utf-8")
    assert '/etc/iachat-router.env' in script
    assert '--port[= ][0-9]+' in script
    assert 'http://127.0.0.1:8000' not in script


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
