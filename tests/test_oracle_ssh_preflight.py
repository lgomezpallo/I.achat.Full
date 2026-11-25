"""Contrato del preflight SSH de Oracle y de su cableado en los workflows.

El fallo real que motivó esto: los workflows morían en un `test -n` genérico y
no se podía distinguir un secreto vacío de una clave no autorizada.
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "oracle_ssh_preflight.sh"
WORKFLOWS = ROOT / ".github" / "workflows"


def run_preflight(env_overrides, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORACLE_")}
    env.pop("GITHUB_STEP_SUMMARY", None)
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )


def test_names_the_single_missing_secret():
    result = run_preflight({"ORACLE_HOST": "144.22.213.171", "ORACLE_USER": "ubuntu"})
    assert result.returncode == 2
    assert "ORACLE_SSH_KEY" in result.stdout
    assert "ORACLE_HOST" not in result.stdout.split("missing=")[-1]
    assert "missing=ORACLE_SSH_KEY" in result.stdout
    # El valor nunca se imprime, ni siquiera vacío entre comillas.
    assert "BEGIN OPENSSH PRIVATE KEY" not in result.stdout


def test_reports_all_three_when_environment_is_empty():
    result = run_preflight({})
    assert result.returncode == 2
    assert "missing=ORACLE_HOST ORACLE_USER ORACLE_SSH_KEY" in result.stdout
    assert result.stdout.count("::error title=Secreto faltante::") == 3


def test_rejects_a_key_without_private_key_header():
    secret = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFalsaSoloPublica"
    result = run_preflight({
        "ORACLE_HOST": "144.22.213.171",
        "ORACLE_USER": "ubuntu",
        "ORACLE_SSH_KEY": secret,
    })
    assert result.returncode == 3
    assert "ORACLE_SSH_KEY" in result.stdout
    assert secret not in result.stdout


def test_rejects_an_unreadable_private_key_without_leaking_it():
    secret = "-----BEGIN OPENSSH PRIVATE KEY-----\nbm90LXVuYS1jbGF2ZS12YWxpZGE=\n-----END OPENSSH PRIVATE KEY-----"
    result = run_preflight({
        "ORACLE_HOST": "144.22.213.171",
        "ORACLE_USER": "ubuntu",
        "ORACLE_SSH_KEY": secret,
    })
    assert result.returncode == 3
    assert "bm90LXVuYS1jbGF2ZS12YWxpZGE" not in result.stdout + result.stderr


def test_every_workflow_with_oracle_ssh_key_runs_the_preflight():
    missing = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text()
        if "secrets.ORACLE_SSH_KEY" not in text:
            continue
        if "bash scripts/oracle_ssh_preflight.sh" not in text:
            missing.append(path.name)
        # Sin checkout el script no existe en el runner.
        if "actions/checkout@" not in text:
            missing.append(path.name + " (sin checkout)")
    assert missing == []


def test_preflight_precedes_the_adhoc_secret_guards():
    text = (WORKFLOWS / "router-readonly-probe.yml").read_text()
    assert re.search(
        r"run: \|\n\s+set -euo pipefail\n\s+bash scripts/oracle_ssh_preflight.sh --connect\n",
        text,
    )
    deploy = (WORKFLOWS / "deploy-oracle.yml").read_text()
    assert deploy.index("oracle_ssh_preflight.sh") < deploy.index('test -n "$ORACLE_HOST"')


def test_oci_run_command_script_is_read_only_and_never_prints_values():
    text = (ROOT / "scripts" / "oci_run_command_router_check.sh").read_text()
    assert "ROUTER_CHECK_MODE=read_only" in text
    for forbidden in ("systemctl restart", "systemctl stop", "router.env >", "cat /etc/iachat/router.env"):
        assert forbidden not in text
    # Solo nombres de variables del env file, nunca el token.
    assert "ROUTER_TOKEN]" not in text
    assert text.count("/etc/iachat/router.env") >= 1
