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
