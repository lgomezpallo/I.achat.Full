"""Verify smoke execution does not access the configured application SQLite."""
import os
import subprocess
import sys
from pathlib import Path


def test_smoke_runner_does_not_create_configured_database(tmp_path):
    production_path = tmp_path / "production-do-not-touch.sqlite"
    env = os.environ.copy()
    env["IACHAT_DB"] = str(production_path)
    env.pop("IACHAT_SMOKE_LIVE", None)
    command = [sys.executable, "scripts/smoke_conversation.py"]
    result = subprocess.run(
        command, cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, timeout=40,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
    assert not production_path.exists(), "Smoke runner accessed configured production SQLite"



def _load_live_preflight():
    """Load the script by path; scripts/ is not an installed Python package."""
    import runpy
    return runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "scripts" / "smoke_conversation.py")
    )["validate_live_backend"]


def _clear_provider_keys(monkeypatch):
    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_live_smoke_defaults_to_integrated_without_router_credentials(monkeypatch):
    """Preflight must not depend on Router or make a real provider request."""
    validate_live_backend = _load_live_preflight()

    monkeypatch.delenv("IACHAT_BACKEND", raising=False)
    monkeypatch.delenv("ROUTER_URL", raising=False)
    monkeypatch.delenv("ROUTER_TOKEN", raising=False)
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "offline-fake-key")
    assert validate_live_backend() == "integrated"


def test_live_smoke_integrated_fails_closed_without_provider(monkeypatch):
    import pytest
    validate_live_backend = _load_live_preflight()

    monkeypatch.setenv("IACHAT_BACKEND", "integrated")
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "offline-fake-token")
    with pytest.raises(SystemExit, match="configured provider"):
        validate_live_backend()


def test_live_smoke_router_requires_explicit_mode_and_credentials(monkeypatch):
    import pytest
    validate_live_backend = _load_live_preflight()

    monkeypatch.setenv("IACHAT_BACKEND", "router")
    monkeypatch.delenv("ROUTER_URL", raising=False)
    monkeypatch.delenv("ROUTER_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="ROUTER_URL and ROUTER_TOKEN"):
        validate_live_backend()
    monkeypatch.setenv("ROUTER_URL", "https://router.example")
    monkeypatch.setenv("ROUTER_TOKEN", "offline-fake-token")
    assert validate_live_backend() == "router"


def test_live_smoke_rejects_unknown_backend_mode(monkeypatch):
    import pytest
    validate_live_backend = _load_live_preflight()

    monkeypatch.setenv("IACHAT_BACKEND", "unknown")
    with pytest.raises(SystemExit, match="Unsupported IACHAT_BACKEND"):
        validate_live_backend()
