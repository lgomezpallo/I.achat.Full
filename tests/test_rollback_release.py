"""Offline rollback regression tests; never touch Oracle or production data."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts" / "rollback_release.py"
DEPLOY = ROOT / "scripts" / "deploy_oracle.sh"


def _write(path: Path, value: str = "test") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_rollback_removes_new_release_files_but_preserves_runtime_data(tmp_path):
    stage, backup, app = (tmp_path / name for name in ("stage", "backup", "app"))
    for folder in (stage, backup, app):
        folder.mkdir()
    _write(stage / "iachat" / "new_feature.py")
    _write(app / "iachat" / "new_feature.py")
    _write(stage / "iachat" / "existing.py", "new")
    _write(backup / "iachat" / "existing.py", "old")
    _write(app / "iachat" / "existing.py", "new")
    _write(stage / "data.db")
    _write(app / "data.db", "runtime database")
    _write(stage / "data.db-wal")
    _write(app / "data.db-wal", "runtime WAL")
    _write(stage / ".venv" / "bin" / "python")
    _write(app / ".venv" / "bin" / "python")
    _write(app / "uploads" / "new-user-file.jpg", "created after backup")

    result = subprocess.run(
        [sys.executable, str(HELPER), str(stage), str(backup), str(app)],
        capture_output=True, text=True, check=True,
    )
    assert "removed 1 new release files" in result.stdout
    assert not (app / "iachat" / "new_feature.py").exists()
    assert (app / "iachat" / "existing.py").read_text() == "new"
    assert (app / "data.db").read_text() == "runtime database"
    assert (app / "data.db-wal").read_text() == "runtime WAL"
    assert (app / ".venv" / "bin" / "python").exists()
    assert (app / "uploads" / "new-user-file.jpg").exists()


def test_rollback_never_follows_symlinked_application_directory(tmp_path):
    stage, backup, app, outside = (tmp_path / name for name in ("stage", "backup", "app", "outside"))
    for folder in (stage, backup, app, outside):
        folder.mkdir()
    _write(stage / "linked" / "new.py")
    _write(outside / "new.py", "do not delete")
    (app / "linked").symlink_to(outside, target_is_directory=True)
    subprocess.run(
        [sys.executable, str(HELPER), str(stage), str(backup), str(app)],
        check=True, capture_output=True, text=True,
    )
    assert (outside / "new.py").read_text() == "do not delete"


def test_deploy_uses_targeted_cleanup_before_backup_restore():
    script = DEPLOY.read_text(encoding="utf-8")
    helper_call = 'python3 "$stage/scripts/rollback_release.py" "$stage" "$backup" "$app"'
    assert helper_call in script
    rollback = script.split("rollback() {", 1)[1].split("\n}", 1)[0]
    assert rollback.index(helper_call) < rollback.index('"$backup/" "$app/"')
    assert "--delete" not in rollback
    assert "rsync -a --checksum " in rollback  # mtime/size collisions must restore old code


def test_rollback_preserves_sqlite_variants_and_environment_files(tmp_path):
    stage, backup, app = (tmp_path / name for name in ("stage", "backup", "app"))
    for folder in (stage, backup, app):
        folder.mkdir()
    protected = (
        "runtime.sqlite", "runtime.sqlite-wal", "runtime.sqlite-shm",
        "runtime.sqlite3", "runtime.sqlite3-journal", "runtime.db",
        "runtime.db-wal", ".env", ".env.local",
    )
    for filename in protected:
        _write(stage / filename, "release")
        _write(app / filename, "runtime: preserve")
    _write(stage / "new_release.py")
    _write(app / "new_release.py")

    result = subprocess.run(
        [sys.executable, str(HELPER), str(stage), str(backup), str(app)],
        check=True, capture_output=True, text=True,
    )
    assert "removed 1 new release files" in result.stdout
    assert not (app / "new_release.py").exists()
    for filename in protected:
        assert (app / filename).read_text() == "runtime: preserve", filename


def test_deploy_excludes_sqlite_and_env_files_in_every_rsync():
    script = DEPLOY.read_text(encoding="utf-8")
    rsync_lines = [line for line in script.splitlines() if "rsync -a " in line]
    assert len(rsync_lines) == 3
    for line in rsync_lines:
        for pattern in (
            "*.db", "*.db-*", "*.sqlite", "*.sqlite-*",
            "*.sqlite3", "*.sqlite3-*", ".env", ".env.*",
        ):
            assert f"--exclude='{pattern}'" in line, pattern


def test_failed_release_restores_original_systemd_dropin():
    """The release must restore service configuration as well as Python files."""
    script = DEPLOY.read_text(encoding="utf-8")
    rollback = script.split("rollback() {", 1)[1].split("\n}", 1)[0]
    backup_call = 'sudo -n cp -p "$dropin" "$dropin_backup"'
    restore_call = 'sudo -n cp -p "$dropin_backup" "$dropin"'
    remove_call = 'sudo -n rm -f "$dropin"'
    assert backup_call in script
    assert restore_call in rollback
    assert remove_call in rollback  # no previous drop-in: remove the new one
    assert script.index(backup_call) < script.index("dropin_changed=1")
    assert script.index("dropin_changed=1") < script.index('sudo -n tee "$dropin"')
    assert rollback.index(restore_call) < rollback.index("systemctl daemon-reload")
    assert rollback.index("systemctl daemon-reload") < rollback.index("systemctl restart iachat")
    assert '"$config_restored" -eq 1' in rollback
    # A failed restore must not be reported as a healthy rollback.
    assert "Rollback health: OK" in rollback


def test_rollback_rehearsal_restores_code_and_preserves_runtime_files(tmp_path):
    """Exercise the same cleanup + rsync sequence in an isolated directory.

    No Oracle access, service restart, credentials, inference or user data.
    """
    stage, backup, app = (tmp_path / name for name in ("stage", "backup", "app"))
    for folder in (stage, backup, app):
        folder.mkdir()
    _write(backup / "iachat" / "app.py", "old working code")
    _write(stage / "iachat" / "app.py", "new failing code")
    _write(app / "iachat" / "app.py", "new failing code")
    _write(stage / "iachat" / "new_module.py", "new release only")
    _write(app / "iachat" / "new_module.py", "new release only")
    _write(stage / ".env.iachat-systemd-rollback", "internal backup")
    _write(app / "runtime.sqlite3", "preserve database")
    _write(app / "runtime.sqlite3-wal", "preserve WAL")
    _write(app / ".env", "preserve local configuration")
    _write(app / "uploads" / "created-after-backup.txt", "preserve upload")

    subprocess.run(
        [sys.executable, str(HELPER), str(stage), str(backup), str(app)],
        check=True, capture_output=True, text=True,
    )
    # Match the deployment rollback's exclusion contract exactly.
    exclusions = (
        ".venv/", ".git/", "*.db", "*.db-*", "*.sqlite", "*.sqlite-*",
        "*.sqlite3", "*.sqlite3-*", ".env", ".env.*",
    )
    subprocess.run(
        ["rsync", "-a", "--checksum", *(f"--exclude={pattern}" for pattern in exclusions),
         str(backup) + "/", str(app) + "/"],
        check=True, capture_output=True, text=True,
    )
    assert (app / "iachat" / "app.py").read_text() == "old working code"
    assert not (app / "iachat" / "new_module.py").exists()
    assert (app / "runtime.sqlite3").read_text() == "preserve database"
    assert (app / "runtime.sqlite3-wal").read_text() == "preserve WAL"
    assert (app / ".env").read_text() == "preserve local configuration"
    assert (app / "uploads" / "created-after-backup.txt").exists()
