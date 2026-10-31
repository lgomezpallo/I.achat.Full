"""Private consistent SQLite snapshot before IAchat deployment; no user data in logs."""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.parse import quote


def backup_database(db_path: Path, target: Path) -> None:
    """Create a private, consistent snapshot without replacing an existing file.

    The file must be 0600 *from creation*, not only after copying sensitive
    conversation content. O_EXCL prevents a symlink or concurrent replacement.
    This helper is independently testable without root or systemd.
    """
    uri = "file:" + quote(str(db_path), safe="/") + "?mode=ro"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(uri, uri=True, timeout=20) as source:
            with sqlite3.connect(str(target), timeout=20) as backup:
                source.backup(backup, pages=200, sleep=0.05)
        with sqlite3.connect(
            "file:" + quote(str(target), safe="/") + "?mode=ro",
            uri=True, timeout=20,
        ) as verify:
            if verify.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("backup_integrity_failed")
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def main() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("root_required_for_service_db_snapshot")
    target_raw = os.environ.get("IACHAT_DB_BACKUP_TARGET", "")
    if not target_raw:
        raise RuntimeError("backup_target_missing")
    target = Path(target_raw).absolute()
    if target.exists():
        raise RuntimeError("backup_target_already_exists")
    pid = int(subprocess.check_output(
        ["systemctl", "show", "iachat", "-p", "MainPID", "--value"],
        text=True, timeout=8).strip())
    if pid <= 1:
        raise RuntimeError("service_not_running")
    proc = Path(f"/proc/{pid}")
    variables = {}
    for entry in (proc / "environ").read_bytes().split(b"\x00"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            if key == b"IACHAT_DB":
                variables["IACHAT_DB"] = value.decode("utf-8", "surrogateescape")
    cwd = Path(os.readlink(str(proc / "cwd")))
    db_path = Path(variables.get("IACHAT_DB", "iachat.db"))
    if not db_path.is_absolute():
        db_path = cwd / db_path
    db_path = db_path.resolve()
    if not db_path.is_file():
        raise RuntimeError("service_database_missing")
    backup_database(db_path, target)
    print("Predeploy SQLite online backup: OK (private, verified)", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Predeploy SQLite backup failed:", type(exc).__name__, flush=True)
        sys.exit(1)
