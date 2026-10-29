#!/usr/bin/env python3
"""Read-only, secret-safe IAchat production diagnostics. Runs on Oracle via SSH stdin.

Never performs inference, reads credential files, changes services, or prints raw logs.
A successful /ready means configuration is present, NOT that providers answer requests.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
APP = Path.home() / "Proyecto/Aplicaciones/IAchat"
KNOWN_DETAILS = {"providers_not_configured", "router_not_configured"}
SIGNALS = (
    "providers_not_configured", "providers_unavailable", "providers_failed",
    "vision_not_configured", "router_not_configured", "router_auth_rejected",
    "router_transport_timeout", "router_transport_connect", "router_failed",
)
HTTP_CODES = ("401", "403", "429")


def command(*args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
        return result.returncode == 0, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False, ""


def probe(path: str) -> dict:
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as response:
            code, raw = response.status, response.read(4096)
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read(4096)
    except (OSError, ValueError):
        return {"http": None}
    result = {"http": code}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return result
    if path == "/ready" and isinstance(data, dict):
        if data.get("mode") in ("integrated", "router"):
            result["mode"] = data["mode"]
        if data.get("detail") in KNOWN_DETAILS:
            result["reason"] = data["detail"]
    return result


def summarize_logs(raw: str) -> dict:
    # Count only allowlisted codes; never print untrusted log lines or free text.
    counts = {signal: 0 for signal in SIGNALS}
    counts.update({"http_" + code + "_mentions": 0 for code in HTTP_CODES})
    for line in raw.splitlines():
        for signal in SIGNALS:
            if re.search(r"(?<![\w])" + re.escape(signal) + r"(?![\w])", line):
                counts[signal] += 1
        for code in HTTP_CODES:
            if re.search(r"(?<!\d)" + code + r"(?!\d)", line):
                counts["http_" + code + "_mentions"] += 1
    return counts


def runtime_hash(name: str) -> str | None:
    path = APP / "iachat" / name
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def build_report() -> dict:
    active, service = command("systemctl", "is-active", "iachat.service")
    _, dropins = command("systemctl", "show", "iachat.service", "-p", "DropInPaths", "--value")
    logs_ok, logs = command(
        "journalctl", "-u", "iachat.service", "--since", "-2 hours",
        "-n", "500", "--no-pager", "-o", "cat",
    )
    return {
        "service": service if service in ("active", "inactive", "failed", "activating") else "unknown",
        "service_command_ok": active,
        "systemd_override_present": bool(dropins),
        "health": probe("/health"),
        "ready": probe("/ready"),
        "private_router_status": probe("/api/router/status"),
        "logs_available": logs_ok,
        "log_signals": summarize_logs(logs) if logs_ok else None,
        "runtime_sha256": {
            "app_py": runtime_hash("app.py"),
            "backend_py": runtime_hash("backend.py"),
        },
        "interpretation": "Read-only. /ready does not prove live inference. HTTP code mentions are not attributed to providers.",
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), sort_keys=True))
