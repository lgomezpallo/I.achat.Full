"""Guardrails for the Oracle deployment workflow (no cloud access needed)."""
from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "deploy-oracle.yml"
)


def test_oracle_deploy_requires_manual_dispatch():
    text = WORKFLOW.read_text(encoding="utf-8")
    triggers = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert "  workflow_dispatch:" in triggers
    for event in ("workflow_run", "push:", "pull_request:", "schedule:"):
        assert event not in triggers, f"Automatic Oracle deployment trigger: {event}"


def test_oracle_deploy_is_gated_to_main_and_explicit_environment():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in text
    assert "environment: oracle-production" in text
    assert "ref: ${{ github.sha }}" in text
    assert "persist-credentials: false" in text
    assert "python -m pytest -q" in text
