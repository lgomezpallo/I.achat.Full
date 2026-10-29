"""Remove only newly introduced release files before restoring a deployment backup.

Never use rsync --delete here: the application directory may contain SQLite,
uploads, credentials or other runtime files created after the backup.
"""
from __future__ import annotations

import fnmatch
import sys
from pathlib import Path


def _protected(relative: Path) -> bool:
    name = relative.name
    # SQLite may use .db, .sqlite or .sqlite3, with -wal/-shm/-journal
    # companions. Local environment files can contain credentials.
    protected_suffixes = (".db", ".sqlite", ".sqlite3")
    return (
        any(part in {".git", ".venv"} for part in relative.parts)
        or name == ".env"
        or name.startswith(".env.")
        or any(
            fnmatch.fnmatch(name, f"*{suffix}")
            or fnmatch.fnmatch(name, f"*{suffix}-*")
            for suffix in protected_suffixes
        )
    )


def remove_new_release_files(stage: Path, backup: Path, app: Path) -> int:
    """Unlink staged files absent from the backup, never directories or user files."""
    removed = 0
    for source in stage.rglob("*"):
        if not (source.is_file() or source.is_symlink()):
            continue
        relative = source.relative_to(stage)
        if _protected(relative):
            continue
        original = backup / relative
        if original.exists() or original.is_symlink():
            continue
        target = app / relative
        # A symlinked parent could redirect deletion outside the app tree.
        parent = app
        unsafe_parent = False
        for component in relative.parts[:-1]:
            parent = parent / component
            if parent.is_symlink():
                unsafe_parent = True
                break
        if unsafe_parent:
            continue
        if target.is_file() or target.is_symlink():
            target.unlink()
            removed += 1
    return removed


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: rollback_release.py STAGE BACKUP APP")
    stage, backup, app = (Path(arg) for arg in sys.argv[1:])
    if not all(path.is_dir() for path in (stage, backup, app)):
        raise SystemExit("rollback directories missing")
    print(f"Rollback: removed {remove_new_release_files(stage, backup, app)} new release files")
