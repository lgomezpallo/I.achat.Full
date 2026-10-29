"""Release reconciliation tests; use only disposable git repos and local files."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile_release.py"
spec = importlib.util.spec_from_file_location("reconcile_release", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def setup_repo(tmp_path):
    app, stage = tmp_path / "app", tmp_path / "stage"
    app.mkdir()
    stage.mkdir()
    subprocess.run(["git", "-C", str(app), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(app), "config", "user.email", "smoke@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(app), "config", "user.name", "Smoke"], check=True)
    source = app / "iachat" / "app.py"
    source.parent.mkdir()
    source.write_text("original\n")
    subprocess.run(["git", "-C", str(app), "add", "."], check=True)
    subprocess.run(["git", "-C", str(app), "commit", "-qm", "baseline"], check=True)
    incoming = stage / "iachat" / "app.py"
    incoming.parent.mkdir()
    incoming.write_text("release\n")
    return app, stage, source, incoming


def test_clean_checkout_needs_no_reconciliation(tmp_path):
    app, stage, *_ = setup_repo(tmp_path)
    assert module.reconcile(app, stage) == 0


def test_byte_identical_tracked_source_is_safe_without_git_reset(tmp_path):
    app, stage, source, _ = setup_repo(tmp_path)
    source.write_text("release\n")
    assert module.reconcile(app, stage) == 1
    # Local edits remain intact and tracked; this is verification, not reset.
    assert subprocess.run(["git", "-C", str(app), "status", "--porcelain"],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_different_source_is_blocked(tmp_path):
    app, stage, source, _ = setup_repo(tmp_path)
    source.write_text("private manual hotfix\n")
    with pytest.raises(ValueError, match="production_source_differs_from_release"):
        module.reconcile(app, stage)
    assert source.read_text() == "private manual hotfix\n"


def test_dirty_configuration_is_never_reconciled(tmp_path):
    app, stage, *_ = setup_repo(tmp_path)
    config = app / ".env"
    config.write_text("original")
    subprocess.run(["git", "-C", str(app), "add", ".env"], check=True)
    subprocess.run(["git", "-C", str(app), "commit", "-qm", "tracked config"], check=True)
    config.write_text("sensitive new value")
    (stage / ".env").write_text("sensitive new value")
    with pytest.raises(ValueError, match="non_source_tracked_change"):
        module.reconcile(app, stage)


def test_symlinked_source_never_passes(tmp_path):
    app, stage, source, incoming = setup_repo(tmp_path)
    source.write_text("release\n")
    incoming.unlink()
    incoming.symlink_to(source)
    with pytest.raises(ValueError, match="production_source_differs_from_release"):
        module.reconcile(app, stage)


def test_staged_or_deleted_source_is_blocked(tmp_path):
    app, stage, source, _ = setup_repo(tmp_path)
    source.unlink()
    with pytest.raises(ValueError, match="unsupported_tracked_change"):
        module.reconcile(app, stage)


def test_deploy_reconciles_before_first_production_rsync():
    script = (ROOT / "scripts" / "deploy_oracle.sh").read_text()
    call = 'python3 "$stage/scripts/reconcile_release.py" "$app" "$stage"'
    assert call in script
    assert script.index('tar -xzf "$archive"') < script.index(call)
    assert script.index(call) < script.index('rsync -a --exclude=')
    assert script.index(call) < script.index("deployed=1")
    assert "git reset" not in script
