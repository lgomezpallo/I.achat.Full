#!/usr/bin/env python3
"""Real free-provider memory E2E in a disposable Oracle process and SQLite DB.

Never reads or writes production conversation data, restarts services, or
discloses provider credentials. Only the isolated child gets the service's
existing free-provider keys; the integrated backend enforces its allowlist.
"""
from __future__ import annotations

import os
import hashlib
import json
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ENV = (
    "GROQ_API_KEY", "GROQ_MODELS", "OPENROUTER_API_KEY",
    "OPENROUTER_MODELS",
)


def recall_flags(answer: str, marker: str) -> tuple[bool, bool, bool]:
    """Check literal, synthetic evidence without printing model output."""
    normalized = re.sub(r"[^A-Z0-9]", "", answer.upper())
    return ("POSTGRESQL" in normalized, marker in normalized, "DIARIO" in normalized)


def transcript_fingerprint(history: list[dict], prefix_count: int = 480) -> str:
    """Digest complete JSON message records, including attachment metadata."""
    if len(history) < prefix_count:
        raise ValueError("transcript_prefix_incomplete")
    canonical = history[:prefix_count]
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_snapshot(path: Path, owner: str, other_owner: str,
                    conversation_id: str, marker: str, count: int,
                    expected_prefix_hash: str | None = None,
                    expected_full_hash: str | None = None) -> bool:
    """Independent SQLite connection: transcript, ledger and owner isolation."""
    from iachat.store import ConversationStore
    store = ConversationStore(str(path))
    try:
        history = store.get(conversation_id, owner)
        summary = store.get_summary(conversation_id, owner)
        return bool(
            history and len(history) == count
            and (expected_prefix_hash is None
                 or transcript_fingerprint(history) == expected_prefix_hash)
            and (expected_full_hash is None
                 or transcript_fingerprint(history, count) == expected_full_hash)
            and history[0]["content"].startswith("Decidimos usar PostgreSQL")
            and marker in history[200]["content"]
            and history[478]["content"].startswith("Corrijo:")
            and summary and summary["processed_count"] == count
            and store.get(conversation_id, other_owner) is None
            and store.get_summary(conversation_id, other_owner) is None
        )
    finally:
        store._db.close()


def launcher(stage: Path) -> None:
    if os.geteuid() != 0:
        raise RuntimeError("root_required_for_isolated_launcher")
    if not stage.is_dir() or stage.resolve() != ROOT:
        raise RuntimeError("invalid_stage_directory")
    pid = int(subprocess.check_output(
        ["systemctl", "show", "iachat", "-p", "MainPID", "--value"],
        text=True, timeout=8,
    ).strip())
    if pid <= 1:
        raise RuntimeError("production_service_not_running")
    proc = Path("/proc") / str(pid)
    uid = proc.stat().st_uid
    if uid == 0:
        raise RuntimeError("refuse_root_service_identity")
    account = pwd.getpwuid(uid)
    installed = Path(os.readlink(str(proc / "cwd"))) / ".venv/bin/python"
    if not installed.is_file():
        raise RuntimeError("production_python_not_found")
    source_env = {}
    for entry in (proc / "environ").read_bytes().split(b"\0"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            name = key.decode("utf-8", "surrogateescape")
            if name in ALLOWED_ENV:
                source_env[name] = value.decode("utf-8", "surrogateescape")
    if not any(source_env.get(key) for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY")):
        raise RuntimeError("no_configured_free_provider_keys")
    # The SSH account and IAchat service account may differ. Give only the
    # unprivileged service UID access to this disposable staging tree.
    os.chown(stage, uid, account.pw_gid)
    os.chmod(stage, 0o700)
    private = Path(tempfile.mkdtemp(prefix=".memory-stage-", dir=stage))
    os.chown(private, uid, account.pw_gid)
    os.chmod(private, 0o700)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": account.pw_dir,
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(stage),
        "PYTHONUNBUFFERED": "1",
        "IACHAT_BACKEND": "integrated",
        "IACHAT_AUTH_SECRET": secrets.token_urlsafe(40),
        "IACHAT_DB": str(private / "isolated.sqlite3"),
    }
    env.update(source_env)
    os.chdir(stage)
    os.initgroups(account.pw_name, account.pw_gid)
    os.setgid(account.pw_gid)
    os.setuid(uid)
    os.execve(str(installed), [str(installed), str(Path(__file__).resolve()),
                               "--child", str(private)], env)


def wait_http(base: str, process: subprocess.Popen, seconds: float = 20.0) -> None:
    import httpx
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("isolated_server_exited")
        try:
            if httpx.get(base + "/health", timeout=1).status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.25)
    raise RuntimeError("isolated_server_not_ready")


def child(private: Path) -> None:
    import httpx
    from iachat.backend import ProviderBackend
    from iachat.store import ConversationStore
    from scripts.backup_iachat_db import backup_database
    from scripts.live_memory_probe import seed_memory_probe

    if os.geteuid() == 0 or not private.is_dir():
        raise RuntimeError("unsafe_child_identity")
    if not ProviderBackend.configured():
        raise RuntimeError("no_allowlisted_free_model_configured")
    db_path = private / "isolated.sqlite3"
    owner, other = "e2e-" + secrets.token_hex(6), "e2e-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    marker = "LUCERO" + secrets.token_hex(4).upper()
    conversation_id = "stage-" + secrets.token_hex(8)
    store = ConversationStore(str(db_path))
    assert store.create_user(owner, password)
    assert store.create_user(other, secrets.token_urlsafe(32))
    seed_memory_probe(store, owner, conversation_id, marker)
    original = store.get(conversation_id, owner)
    if original is None or len(original) != 480:
        raise AssertionError("seeded_transcript_incomplete")
    expected_prefix_hash = transcript_fingerprint(original)
    store._db.close()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    cmd = [sys.executable, "-m", "uvicorn", "iachat.app:app",
           "--host", "127.0.0.1", "--port", str(port), "--no-access-log"]
    process = None

    def start() -> subprocess.Popen:
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=os.environ.copy(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            wait_http(base, proc)
        except BaseException:
            # A failed readiness probe must not leave an orphan staging server.
            stop(proc)
            raise
        return proc

    def stop(proc: subprocess.Popen) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    try:
        process = start()
        with httpx.Client(base_url=base, timeout=160, follow_redirects=False) as client:
            login = client.post("/auth/login", json={"username": owner, "password": password})
            if login.status_code != 200:
                raise AssertionError("isolated_authentication_failed")
            cookie = login.cookies.get("iachat_session")
            if not cookie:
                raise AssertionError("isolated_session_missing")
            client.headers["Cookie"] = "iachat_session=" + cookie
            first = client.post("/api/chat", json={
                "conversation_id": conversation_id, "project": "Atlas",
                "text": ("Según ESTA conversación del proyecto Atlas, ¿qué base de datos "
                         "elegimos, qué código de motor tiene Violeta y cada cuánto "
                         "será el respaldo? Respondé los tres datos sin inventar."),
            })
            answer = first.json().get("answer", "") if first.status_code == 200 else ""
            flags = recall_flags(answer, marker)
            if first.status_code != 200 or not all(flags):
                raise AssertionError("live_free_provider_recall_failed")
            if not verify_snapshot(db_path, owner, other, conversation_id, marker, 482, expected_prefix_hash):
                raise AssertionError("first_live_transcript_not_durable")
            first_history = ConversationStore(str(db_path))
            try:
                first_hash = transcript_fingerprint(
                    first_history.get(conversation_id, owner), 482
                )
            finally:
                first_history._db.close()
            print("STAGE_LIVE_MEMORY_480: PASS (begin/middle/end)", flush=True)
        stop(process)
        process = None

        # Simulate a three-week gap on this disposable database only.
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE conversation_index SET updated_at=updated_at-21*86400 "
                "WHERE id=? AND owner=?", (conversation_id, owner))
        process = start()
        with httpx.Client(base_url=base, timeout=160, follow_redirects=False) as client:
            login = client.post("/auth/login", json={"username": owner, "password": password})
            if login.status_code != 200:
                raise AssertionError("restarted_authentication_failed")
            client.headers["Cookie"] = "iachat_session=" + login.cookies["iachat_session"]
            restored = client.get("/api/conversations/" + conversation_id)
            if restored.status_code != 200 or len(restored.json().get("history", [])) != 482:
                raise AssertionError("restart_lost_conversation")
            if transcript_fingerprint(restored.json()["history"], 482) != first_hash:
                raise AssertionError("restart_modified_transcript")
            followup = client.post("/api/chat", json={
                "conversation_id": conversation_id, "project": "Atlas",
                "text": "¿Cuál era el código exacto del motor Violeta que decidimos?",
            })
            answer = followup.json().get("answer", "") if followup.status_code == 200 else ""
            if followup.status_code != 200 or marker not in re.sub(r"[^A-Z0-9]", "", answer.upper()):
                raise AssertionError("live_recall_after_restart_failed")
        final_store = ConversationStore(str(db_path))
        try:
            final_hash = transcript_fingerprint(
                final_store.get(conversation_id, owner), 484
            )
        finally:
            final_store._db.close()
        if not verify_snapshot(db_path, owner, other, conversation_id, marker, 484,
                               expected_prefix_hash, final_hash):
            raise AssertionError("restart_transcript_not_durable")
        print("STAGE_RESTART_21_DAYS_AND_LIVE_RECALL: PASS", flush=True)

        # Restore a real SQLite online backup into a second independent store.
        backup_path = private / "restored.sqlite3"
        backup_database(db_path, backup_path)
        if stat.S_IMODE(backup_path.stat().st_mode) != 0o600:
            raise AssertionError("backup_permissions_not_private")
        if not verify_snapshot(backup_path, owner, other, conversation_id, marker, 484,
                               expected_prefix_hash, final_hash):
            raise AssertionError("restored_backup_missing_memory")
        print("STAGE_BACKUP_RESTORE_OWNER_ISOLATION: PASS", flush=True)
    finally:
        if process is not None:
            stop(process)
        shutil.rmtree(private)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] not in ("--launch", "--child"):
            raise RuntimeError("usage: --launch|--child STAGE_OR_PRIVATE_DIR")
        if sys.argv[1] == "--launch":
            launcher(Path(sys.argv[2]))
        else:
            child(Path(sys.argv[2]))
    except Exception as exc:
        # No secrets, model answers, user data or generated markers in logs.
        print("STAGE_LIVE_MEMORY_FAILURE:", type(exc).__name__,
              str(exc)[:100], flush=True)
        sys.exit(1)
