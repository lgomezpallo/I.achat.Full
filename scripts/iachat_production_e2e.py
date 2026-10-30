"""Authenticated, real HTTP production smoke; isolated temporary account, no secrets in logs.

Invoked after the release has started. The privileged launcher reads the running
service environment in memory and drops to the service UID before importing the
application or touching SQLite. No existing user credentials are read or changed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import sqlite3
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"
QUESTIONS = (
    "¿Cuándo es el próximo partido de River Plate? Indicá fecha, horario y URL de una fuente comprobable.",
    "¿Cuál es la cotización del dólar oficial en Argentina hoy? Indicá el valor y URL de la fuente consultada.",
)
GENERIC = re.compile(
    r"(?i)(no (?:dispongo|tengo|cuento) (?:con |de )?(?:datos|informaci[oó]n) actualizad|"
    r"no (?:tengo acceso|puedo acceder) (?:a |al )?(?:internet|la web|datos en tiempo real)|"
    r"consult[aá] (?:la p[aá]gina|un sitio|sitios))"
)


def launcher() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("launcher_requires_root")
    pid = int(subprocess.check_output(
        ["systemctl", "show", "iachat", "-p", "MainPID", "--value"],
        text=True, timeout=8,
    ).strip())
    if pid <= 1:
        raise RuntimeError("iachat_process_not_running")
    process = Path(f"/proc/{pid}")
    raw = (process / "environ").read_bytes()
    service_env = {}
    for entry in raw.split(b"\x00"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            service_env[key.decode("utf-8", "surrogateescape")] = value.decode("utf-8", "surrogateescape")
    if not service_env.get("IACHAT_AUTH_SECRET"):
        raise RuntimeError("production_auth_secret_missing")
    if service_env.get("IACHAT_BACKEND", "integrated").lower() != "integrated":
        raise RuntimeError("production_backend_not_integrated")
    uid = process.stat().st_uid
    user = pwd.getpwuid(uid)
    cwd = os.readlink(str(process / "cwd"))
    python = ROOT / ".venv/bin/python"
    if not python.is_file():
        raise RuntimeError("production_virtualenv_missing")
    service_env["PYTHONPATH"] = str(ROOT)
    service_env["IACHAT_E2E_EXPECTED_APP_SHA256"] = os.getenv("IACHAT_E2E_EXPECTED_APP_SHA256", "")
    os.chdir(cwd)
    os.initgroups(user.pw_name, user.pw_gid)
    os.setgid(user.pw_gid)
    os.setuid(uid)
    os.execve(str(python), [str(python), str(Path(__file__).resolve()), "--child"], service_env)


def cleanup_account(db_path: str, username: str) -> None:
    with sqlite3.connect(db_path, timeout=20) as connection:
        for table in ("workspace_files", "automatic_memory_log", "memories",
                      "conversation_index", "conversations", "image_attachments"):
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "owner" in columns:
                    connection.execute(f"DELETE FROM {table} WHERE owner=?", (username,))
        connection.execute("DELETE FROM users WHERE username=?", (username,))


def stage_evidence(question: str) -> tuple[int, set[str]]:
    from iachat.web_planner import plan_web_lookup_semantic
    from iachat.web_research import web_evidence_with_pages
    from iachat.backend import ProviderBackend
    plan = plan_web_lookup_semantic(question, [], ProviderBackend())
    print("PLANNER:", plan.action, plan.reason, "query=", repr(plan.query[:160]), flush=True)
    if plan.action != "search":
        raise AssertionError("planner_skipped_current_question")
    evidence = web_evidence_with_pages(plan.query, news_fallback=True)
    sources: set[str] = set()
    try:
        start = evidence.index("[")
        records, _ = json.JSONDecoder().raw_decode(evidence[start:])
        for item in records:
            url = item.get("url")
            if isinstance(url, str) and urlsplit(url).scheme == "https":
                sources.add(url)
    except (ValueError, TypeError, KeyError):
        pass
    print("WEB_EVIDENCE:", "sources", len(sources), "bytes", len(evidence.encode("utf-8")), flush=True)
    print("WEB_SOURCE_HOSTS:", ",".join(sorted({urlsplit(u).hostname or "" for u in sources})[:5]), flush=True)
    return len(sources), sources


def child() -> None:
    import httpx
    from iachat.store import ConversationStore
    from iachat.backend import ProviderBackend

    # All live model requests go through the existing fail-closed free-model allowlist.
    if not ProviderBackend.configured():
        raise AssertionError("free_provider_not_configured")
    db_path = os.getenv("IACHAT_DB", "iachat.db")
    if db_path == ":memory:":
        raise AssertionError("production_database_is_memory_only")
    db_path = str(Path(db_path).resolve())
    if not Path(db_path).is_file():
        raise AssertionError("production_database_not_found")
    expected = os.getenv("IACHAT_E2E_EXPECTED_APP_SHA256", "")
    actual = hashlib.sha256((ROOT / "iachat/app.py").read_bytes()).hexdigest()
    print("RELEASE_APP_SHA256:", actual, flush=True)
    if expected and actual != expected:
        raise AssertionError("deployed_source_hash_mismatch")

    username = "e2e-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    store = ConversationStore(db_path)
    if not store.create_user(username, password):
        raise AssertionError("temporary_user_creation_failed")
    try:
        with httpx.Client(base_url=BASE, timeout=160.0, follow_redirects=False) as client:
            login = client.post("/auth/login", json={"username": username, "password": password})
            print("AUTH_LOGIN_HTTP:", login.status_code, flush=True)
            if login.status_code != 200:
                raise AssertionError("real_login_failed")
            cookie = login.cookies.get("iachat_session")
            if not cookie:
                raise AssertionError("login_cookie_missing")
            # The production cookie has Secure; the internal HTTP loopback smoke
            # must explicitly send it (the public browser continues using HTTPS).
            client.headers["Cookie"] = "iachat_session=" + cookie
            status = client.get("/auth/status")
            if status.status_code != 200 or status.json().get("username") != username:
                raise AssertionError("real_cookie_auth_failed")
            spec = client.get("/openapi.json")
            if spec.status_code != 200 or "/api/files/generate" not in spec.json().get("paths", {}):
                raise AssertionError("new_release_not_served")
            print("AUTH_COOKIE_AND_FILE_ROUTES: OK", flush=True)

            failures = []
            # Ordinary inference must work independently of web search.
            try:
                normal = client.post("/api/chat", json={"text": "¿Cuánto es 7 por 8? Respondé con el resultado."})
                normal_answer = normal.json().get("answer", "") if normal.status_code == 200 else ""
                normal_ok = normal.status_code == 200 and "56" in normal_answer
                print("NORMAL_CHAT:", "OK" if normal_ok else f"HTTP_{normal.status_code}", flush=True)
                if not normal_ok:
                    failures.append("normal_chat_failed")
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                print("NORMAL_CHAT_ERROR:", type(exc).__name__, flush=True)
                failures.append("normal_chat_http_error")
            for idx, question in enumerate(QUESTIONS, 1):
                count, sources = stage_evidence(question)
                if not count:
                    failures.append(f"web_{idx}_no_sources")
                try:
                    response = client.post("/api/chat", json={"text": question})
                    answer = response.json().get("answer", "") if response.status_code == 200 else ""
                    urls = set(re.findall(r"https://[^\s)<>]+", answer))
                    matched = any(u.rstrip(".,;") in sources for u in urls)
                    generic = bool(GENERIC.search(answer))
                    print(f"CHAT_{idx}: http={response.status_code} chars={len(answer)} "
                          f"generic={generic} cited_source={matched}", flush=True)
                    if response.status_code != 200 or generic or not matched:
                        failures.append(f"chat_{idx}_missing_grounded_answer")
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    print(f"CHAT_{idx}: error={type(exc).__name__}", flush=True)
                    failures.append(f"chat_{idx}_http_error")

            # Deterministic real authenticated file creation and byte-exact download.
            payload = {"name": "e2e-verificacion.csv", "content": "nombre,valor\nprueba,123\n"}
            saved = client.post("/api/files", json=payload)
            if saved.status_code != 201:
                failures.append("file_create_failed")
            else:
                file_id = saved.json()["id"]
                downloaded = client.get(f"/api/files/{file_id}/download")
                match = downloaded.status_code == 200 and downloaded.content == payload["content"].encode()
                print("FILE_DOWNLOAD:", "OK" if match else "FAILED", flush=True)
                if not match:
                    failures.append("file_download_mismatch")
            # Model-generated file: real authenticated provider inference.
            try:
                generated = client.post("/api/files/generate", json={
                    "instruction": "Creá un archivo llamado resumen-e2e.txt cuyo contenido sea exactamente: Prueba IAchat OK."
                })
                generated_ok = generated.status_code == 201
                if generated_ok:
                    info = generated.json()
                    result = client.get(f"/api/files/{info['id']}/download")
                    generated_ok = result.status_code == 200 and b"Prueba IAchat OK" in result.content
                print("MODEL_FILE_GENERATION:", "OK" if generated_ok else f"HTTP_{generated.status_code}", flush=True)
                if not generated_ok:
                    failures.append("model_file_generation_failed")
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                print("MODEL_FILE_GENERATION_ERROR:", type(exc).__name__, flush=True)
                failures.append("model_file_generation_error")
            if failures:
                raise AssertionError("E2E_FAILED:" + ",".join(failures))
            print("E2E_AUTH_WEB_CHAT_FILES: PASS", flush=True)
    finally:
        cleanup_account(db_path, username)
        print("TEMPORARY_ACCOUNT_AND_DATA: CLEANED", flush=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise RuntimeError("usage: script --launch|--child")
        if sys.argv[1] == "--launch":
            launcher()
        elif sys.argv[1] == "--child":
            child()
        else:
            raise RuntimeError("invalid_mode")
    except Exception as exc:
        # No secrets, response bodies or production data in logs.
        print("E2E_FAILURE:", type(exc).__name__, str(exc)[:200], flush=True)
        sys.exit(1)
