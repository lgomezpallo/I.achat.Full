"""Targeted offline checks for the explicitly approved release recovery path."""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'rollback_oracle.sh'
WORKFLOW = ROOT / '.github' / 'workflows' / 'rollback-oracle.yml'
DEPLOY_WORKFLOW = ROOT / '.github' / 'workflows' / 'deploy-oracle.yml'
DEPLOY = ROOT / 'scripts' / 'deploy_oracle.sh'


def test_rollback_shell_parses_and_requires_existing_snapshot():
    subprocess.run(['bash', '-n', str(SCRIPT)], check=True)
    result = subprocess.run(['bash', str(SCRIPT), 'abc'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'invalid_release_run_id' in result.stdout


def test_rollback_is_manual_main_only_with_protected_environment():
    workflow = WORKFLOW.read_text()
    assert 'workflow_dispatch:' in workflow
    assert 'schedule:' not in workflow
    assert 'push:' not in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "inputs.confirmation == 'ROLLBACK'" in workflow
    assert 'environment: oracle-production' in workflow
    assert 'StrictHostKeyChecking=yes' in workflow
    # La huella del host se declara en el deploy; el rollback debe usar la misma,
    # sin una segunda copia que pueda quedar desactualizada.
    pinned = re.search(r"expected=['\"](SHA256:[A-Za-z0-9+/=]+)['\"]", DEPLOY_WORKFLOW.read_text())
    assert pinned, 'deploy-oracle.yml must pin the Oracle host key'
    assert pinned.group(1) in workflow


def test_rollback_requires_clean_release_and_preserves_private_data():
    script = SCRIPT.read_text()
    assert 'newer_release_snapshot_exists' in script
    assert 'deployed_code_has_drift_manual_review_required' in script
    assert 'systemd_configuration_has_drift' in script
    assert '--checksum' in script
    assert 'rollback_release.py' in script
    assert '--delete' not in script
    for pattern in ('*.db', '*.sqlite', '*.sqlite3', '.env', '.venv/', '.git/'):
        assert "--exclude='" + pattern + "'" in script
    assert 'live_inference=not_verified' in script


def test_successful_deploy_retains_dropin_integrity_marker():
    script = DEPLOY.read_text()
    assert 'sha256sum "$dropin"' in script
    assert '.dropin-deployed-sha256' in script
    assert script.index('sha256sum "$dropin"') < script.rindex('deployed=0')
