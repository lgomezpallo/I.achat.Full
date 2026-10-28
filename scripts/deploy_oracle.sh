#!/usr/bin/env bash
# Runs on Oracle, receives the GitHub run ID. Requires existing ubuntu sudo permissions.
set -Eeuo pipefail
run_id="${1:?missing_run_id}"
[[ "$run_id" =~ ^[0-9]+$ ]] || { echo "invalid_run_id"; exit 1; }
app="$HOME/Proyecto/Aplicaciones/IAchat"
archive="/tmp/iachat-release-${run_id}.tar.gz"
stage="$(mktemp -d)"
backup="$(mktemp -d)"
deployed=0
cleanup() { rm -rf "$stage" "$backup"; rm -f "$archive"; }
rollback() {
  status=$?
  if [[ "$status" -ne 0 && "$deployed" -eq 1 ]]; then
    echo "Deployment failed; reverting application code."
    # Only remove files introduced by this release; preserve runtime data.
    python3 "$stage/scripts/rollback_release.py" "$stage" "$backup" "$app" || \
      echo "::error::New release file cleanup failed; manual inspection required."
    rsync -a --exclude='.venv/' --exclude='.git/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
      "$backup/" "$app/" || true
    "$app/.venv/bin/python" -m pip install -e "$app" --disable-pip-version-check -q || true
sudo -n systemctl restart iachat || true
    if sudo -n systemctl is-active --quiet iachat && curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null; then
      echo "Rollback health: OK (inference not verified)"
    else
      echo "::error::Rollback health check failed; manual recovery required."
    fi
  fi
  cleanup
  exit "$status"
}
trap rollback EXIT
test -f "$archive"
test -d "$app/.venv"
test -d "$app/.git"
command -v rsync >/dev/null
command -v python3 >/dev/null
tar -xzf "$archive" -C "$stage" --no-same-owner
test -f "$stage/pyproject.toml"
test -f "$stage/iachat/app.py"
# Preserve local repository, SQLite data, secrets, and Python environment.
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
  "$app/" "$backup/"
deployed=1
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
  "$stage/" "$app/"
"$app/.venv/bin/python" -m pip install -e "$app" --disable-pip-version-check -q
"$app/.venv/bin/python" -m compileall -q "$app/iachat"
# Load existing provider credentials directly into IAchat (never echo secrets).
# A literal newline, not a backslash-n, is required in a systemd drop-in.
provider_file=""
for candidate in /etc/router-providers.env "$HOME/.config/router/providers.env"; do
  if sudo -n test -s "$candidate"; then
    provider_file="$candidate"
    break
  fi
done
if [[ -z "$provider_file" ]]; then
  echo "::error::No provider credential file found on Oracle."
  exit 1
fi
sudo -n install -d -m 755 /etc/systemd/system/iachat.service.d
printf '[Service]\nEnvironmentFile=%s\nEnvironment=IACHAT_BACKEND=integrated\n' "$provider_file" | sudo -n tee /etc/systemd/system/iachat.service.d/20-integrated-providers.conf >/dev/null
sudo -n systemctl daemon-reload
sudo -n systemctl restart iachat
sudo -n systemctl is-active --quiet iachat
# /health checks process availability; no inference request is made.
"$app/.venv/bin/python" - <<'PY'
import time
import urllib.request
for attempt in range(12):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
            if response.status == 200:
                print("IAchat deployment: health OK")
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("IAchat health check failed")
PY
# Readiness must verify that credentials reached IAchat, not only process health.
curl -fsS --max-time 10 http://127.0.0.1:8000/ready | grep -q '"mode":"integrated"'
test "$(curl -fsS http://127.0.0.1:8000/ | grep -c 'id="projectScope"')" -ge 1 || { echo "Project selector missing from served app"; exit 1; }
# Explicit postdeploy checks: ensure the configured integrated minirouter is active.
"$app/.venv/bin/python" - <<'PY'
import json
import urllib.error
import urllib.request
base = "http://127.0.0.1:8000"
def probe(path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, None
code, status = probe("/api/router/status")
assert code == 200 and status.get("mode") == "integrated" and status.get("configured") is True, "Integrated providers unavailable"
code, _ = probe("/api/conversations")
assert code == 401, "Private conversations API not protected"
print("Postdeploy: minirouter configuration and authentication checks OK")
PY
deployed=0
echo "IAchat deployed successfully (live inference not verified)"
