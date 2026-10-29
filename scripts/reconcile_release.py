#!/usr/bin/env python3
"""Fail-closed reconciliation of tracked Oracle edits against a staged release.

Only source files whose bytes already equal the incoming release can be
considered reconciled. Never reset git, print local filenames, read secrets,
or authorize overwriting a differing production file.
"""
from __future__ import annotations

import filecmp
import re
import subprocess
import sys
from pathlib import Path

SAFE_SOURCE = re.compile(
    r"(?:iachat|scripts)/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.(?:py|sh)\Z"
)


def _regular_inside(root: Path, relative: str) -> Path | None:
    path = root / relative
    current = root
    for component in Path(relative).parts:
        current = current / component
        if current.is_symlink():
            return None
    if not path.is_file():
        return None
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            return None
    except OSError:
        return None
    return path


def reconcile(app: Path, stage: Path) -> int:
    result = subprocess.run(
        ["git", "-C", str(app), "status", "--porcelain=v1", "-z", "--untracked-files=no"],
        check=True, capture_output=True, timeout=15,
    )
    entries = result.stdout.split(b"\0")
    if entries[-1] != b"":
        raise ValueError("incomplete_git_status")
    count = 0
    for entry in entries[:-1]:
        if len(entry) < 4 or entry[:2] not in (b" M", b"M ", b"MM"):
            raise ValueError("unsupported_tracked_change")
        try:
            relative = entry[3:].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("unsupported_tracked_path") from exc
        if not SAFE_SOURCE.fullmatch(relative):
            raise ValueError("non_source_tracked_change")
        current = _regular_inside(app, relative)
        incoming = _regular_inside(stage, relative)
        if current is None or incoming is None or not filecmp.cmp(current, incoming, shallow=False):
            raise ValueError("production_source_differs_from_release")
        count += 1
    return count


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: reconcile_release.py APP STAGE")
    try:
        matched = reconcile(Path(sys.argv[1]), Path(sys.argv[2]))
    except (ValueError, OSError, subprocess.SubprocessError):
        raise SystemExit("tracked_production_changes_require_manual_reconciliation")
    print(f"matched_tracked_source_files={matched}")
