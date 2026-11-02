#!/usr/bin/env python3
"""One authenticated HTTPS turn against installed IAchat, with DB and second-session readback.

Diagnostic only: uses the installed backend and temporary user, never deploys or
changes a service. Prints only status codes and safe check labels, not content.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import secrets
import subprocess
import sys

APP = Path("/home/ubuntu/Proyecto/Aplicaciones/IAchat")
ORIGIN = "https://ia-chat.duckdns.org"


class ProbeError(Exception):
    pass


def launch() -> None:
    if os.geteuid() != 0:
        raise ProbeError("root_launcher_required")
    pid_text = subprocess.check_output(
        ["systemctl", "show", "iachat", "-p", "MainPID", "--value"],
        text=True, timeout=8,
    ).strip()
    if not pid_text.isdigit() or int(pid_text) <= 1:
        raise ProbeError("iachat_process_not_running")
    proc = Path("/proc") / pid_text
    service_env = {}
    for entry in (proc / "environ").read_bytes().split(b"\x00"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            service_env[key.decode("utf-8", "surrogateescape")] = value.decode(
                "utf-8", "surrogateescape"
            )
    if service_env.get("IACHAT_BACKEND", "integrated").lower() != "integrated":
        raise ProbeError("integrated_backend_required")
    if not service_env.get("IACHAT_AUTH_SECRET"):
        raise ProbeError("auth_not_configured")
    python = APP / ".venv/bin/python"
    if not python.is_file():
        raise ProbeError("installed_virtualenv_missing")
    uid = proc.stat().st_uid
    user = pwd.getpwuid(uid)
    os.chdir(os.readlink(str(proc / "cwd")))
    service_env["PYTHONPATH"] = str(APP)
    os.initgroups(user.pw_name, user.pw_gid)
    os.setgid(user.pw_gid)
    os.setuid(uid)
    os.execve(str(python), [str(python), str(Path(__file__).resolve()), "--child"], service_env)


def check_http(response, label: str) -> dict:
    print(label + "_HTTP=" + str(response.status_code), flush=True)
    if response.status_code != 200:
        raise ProbeError(label.lower() + "_http_" + str(response.status_code))
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProbeError(label.lower() + "_invalid_json") from exc
    if not isinstance(payload, dict):
        raise ProbeError(label.lower() + "_invalid_payload")
    return payload


def child() -> None:
    import httpx
    from iachat.backend import ProviderBackend
    from iachat.store import ConversationStore
    from scripts.iachat_production_e2e import cleanup_account

    if not ProviderBackend.configured():
        raise ProbeError("no_configured_allowlisted_free_provider")
    db_path = os.getenv("IACHAT_DB", "iachat.db")
    if db_path == ":memory:" or not Path(db_path).resolve().is_file():
        raise ProbeError("persistent_iachat_db_not_found")
    store = ConversationStore(db_path)
    username = "e2e-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    if not store.create_user(username, password):
        raise ProbeError("temporary_user_creation_failed")

    try:
        with httpx.Client(base_url=ORIGIN, timeout=110, follow_redirects=False) as client:
            login = check_http(
                client.post("/auth/login", json={"username": username, "password": password}),
                "LOGIN",
            )
            if login.get("username") != username:
                raise ProbeError("login_identity_mismatch")
            status = check_http(client.get("/auth/status"), "SESSION")
            if not status.get("authenticated") or status.get("username") != username:
                raise ProbeError("session_cookie_not_accepted")

            prompt = "¿Cuánto es 7 por 8? Respondé únicamente con el número 56."
            response = check_http(client.post("/api/chat", json={"text": prompt}), "CHAT")
            answer = response.get("answer")
            conversation_id = response.get("conversation_id")
            if not isinstance(answer, str) or "56" not in answer or not isinstance(conversation_id, str):
                raise ProbeError("real_model_answer_missing_or_unexpected")
            print("REAL_MODEL_RESPONSE=PASS", flush=True)

        # New HTTPS client and login: no reuse of the first browser session.
        with httpx.Client(base_url=ORIGIN, timeout=25, follow_redirects=False) as second:
            check_http(
                second.post("/auth/login", json={"username": username, "password": password}),
                "SECOND_LOGIN",
            )
            restored = check_http(
                second.get("/api/conversations/" + conversation_id), "SECOND_SESSION_READ",
            )
        history = restored.get("history")
        stored = store.get(conversation_id, username)
        if not isinstance(history, list) or len(history) < 2 or history != stored:
            raise ProbeError("database_or_http_history_mismatch")
        if (history[-2].get("role") != "user"
                or history[-2].get("content") != prompt
                or history[-1].get("role") != "assistant"
                or history[-1].get("content") != answer):
            raise ProbeError("persisted_turn_not_matching_response")
        print("AUTHENTICATED_HTTPS_TURN_AND_DB_PERSISTENCE=PASS", flush=True)
    finally:
        cleanup_account(db_path, username)
        print("TEMPORARY_TEST_ACCOUNT_CLEANED=YES", flush=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ("--launch", "--child"):
            raise ProbeError("usage_launch_or_child")
        launch() if sys.argv[1] == "--launch" else child()
    except ProbeError as exc:
        print("ONE_TURN_FAILURE=" + str(exc), flush=True)
        sys.exit(1)
    except Exception as exc:
        # Never print exception messages, URLs, credentials, cookies, or model text.
        print("ONE_TURN_FAILURE_CLASS=" + type(exc).__name__, flush=True)
        sys.exit(1)
