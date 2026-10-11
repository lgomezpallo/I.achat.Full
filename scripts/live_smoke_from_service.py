#!/usr/bin/env python3
"""Run an isolated smoke test with Router settings from IAchat's running process.

No secret values are logged. Requires local sudo permission to read the service
process environment. No services or persistent databases are modified.
"""
import os
import subprocess
import sys

pid = subprocess.check_output(
    ["systemctl", "show", "iachat", "--property=MainPID", "--value"], text=True
).strip()
if not pid.isdigit() or int(pid) < 2:
    raise SystemExit("iachat service not running")
raw = subprocess.run(
    ["sudo", "-n", "cat", "/proc/" + pid + "/environ"],
    capture_output=True, check=False,
)
if raw.returncode:
    raise SystemExit("cannot read IAchat service runtime environment")
service_env = {}
for item in raw.stdout.split(b"\0"):
    key, separator, val = item.partition(b"=")
    if separator and key in (b"ROUTER_URL", b"ROUTER_TOKEN"):
        service_env[key.decode()] = val.decode()
if not all(service_env.get(key) for key in ("ROUTER_URL", "ROUTER_TOKEN")):
    raise SystemExit("ROUTER_URL/ROUTER_TOKEN not present in service runtime")
env = os.environ.copy()
env.update(service_env)
env["IACHAT_SMOKE_LIVE"] = "1"
# Import-time db path is overridden by the isolated smoke runner.
os.execve(sys.executable, [sys.executable, "scripts/smoke_conversation.py"], env)
