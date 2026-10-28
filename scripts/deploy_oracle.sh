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
# Keep the previous systemd override for a real configuration rollback.
dropin="/etc/systemd/system/iachat.service.d/20-integrated-providers.conf"
dropin_backup="$stage/.env.iachat-systemd-rollback"
dropin_existed=0
dropin_changed=0
cleanup() { rm -rf "$stage" "$backup"; rm -f "$archive"; }
rollback() {
  status=$?
  if [[ "$status" -ne 0 && "$deployed" -eq 1 ]]; then
    echo "Deployment failed; reverting application code."
    # Only remove files introduced by this release; preserve runtime data.
    rollback_ok=1
    if ! python3 "$stage/scripts/rollback_release.py" "$stage" "$backup" "$app"; then
      rollback_ok=0
      echo "::error::New release file cleanup failed; manual inspection required."
    fi
    # --checksum avoids rsync skipping changed files with identical size/mtime.
    if ! rsync -a --checksum --exclude='.venv/' --exclude='.git/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
      "$backup/" "$app/"; then
      rollback_ok=0
      echo "::error::Previous application files could not be fully restored."
    fi
    if ! "$app/.venv/bin/python" -m pip install -e "$app" --disable-pip-version-check -q; then
      rollback_ok=0
      echo "::error::Previous application dependencies could not be restored."
    fi
    # Restore the original backend configuration before restarting old code.
    config_restored=1
    if [[ "$dropin_changed" -eq 1 ]]; then
      if [[ "$dropin_existed" -eq 1 ]]; then
        sudo -n cp -p "$dropin_backup" "$dropin" || config_restored=0
      else
        sudo -n rm -f "$dropin" || config_restored=0
      fi
      sudo -n systemctl daemon-reload || config_restored=0
    fi
    if ! sudo -n systemctl restart iachat; then
      rollback_ok=0
      echo "::error::Previous IAchat service could not be restarted."
    fi
    # Health alone cannot prove rollback: all restore operations must succeed.
    if [[ "$rollback_ok" -eq 1 && "$config_restored" -eq 1 ]] && sudo -n systemctl is-active --quiet iachat && curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null; then
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
# This file changes service behavior and must be reverted together with code.
# The private staging directory is removed by the EXIT trap; never log content.
if sudo -n test -e "$dropin"; then
  sudo -n cp -p "$dropin" "$dropin_backup"
  dropin_existed=1
fi
dropin_changed=1
printf '[Service]\nEnvironmentFile=%s\nEnvironment=IACHAT_BACKEND=integrated\n' "$provider_file" | sudo -n tee "$dropin" >/dev/null
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
