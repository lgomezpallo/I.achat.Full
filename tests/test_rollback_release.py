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
