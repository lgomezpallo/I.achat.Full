#!/usr/bin/env bash
# Runs on Oracle, receives the GitHub run ID. Requires existing ubuntu sudo permissions.
set -Eeuo pipefail
run_id="${1:?missing_run_id}"
deploy_started_epoch="$(date +%s)"
[[ "$run_id" =~ ^[0-9]+$ ]] || { echo "invalid_run_id"; exit 1; }
app="$HOME/Proyecto/Aplicaciones/IAchat"
archive="/tmp/iachat-release-${run_id}.tar.gz"
# Keep an operator-recoverable snapshot after a successful deployment.
# Do not include SQLite, .env files, or the virtualenv in the code backup.
# Every snapshot is private and tied to the immutable GitHub run ID.
umask 077
recovery_base="$HOME/.local/state/iachat-releases"
install -d -m 700 "$recovery_base"
recovery_dir="$(mktemp -d "$recovery_base/${run_id}.XXXXXX")"
stage="$recovery_dir/stage"
backup="$recovery_dir/backup"
mkdir -m 700 "$stage" "$backup"
deployed=0
# Keep the previous systemd override for a real configuration rollback.
dropin="/etc/systemd/system/iachat.service.d/20-integrated-providers.conf"
dropin_backup="$stage/.env.iachat-systemd-rollback"
dropin_existed=0
dropin_changed=0
cleanup() { rm -rf -- "$recovery_dir"; rm -f "$archive"; }
rollback() {
  status=$?
  rollback_incomplete=0
  if [[ "$status" -eq 0 ]]; then
    # The previous code and systemd drop-in must remain available for an
    # explicitly approved post-deployment rollback. Never print their contents.
    rm -f "$archive"
    echo "Recovery snapshot retained for authorized rollback: $recovery_dir"
    return 0
  fi
  if [[ "$status" -ne 0 && "$deployed" -eq 1 ]]; then
    echo "Deployment failed; reverting application code."
    # Only allowlisted status metadata from this deployment. Never emit raw
    # journal entries, prompts, response bodies or credential-bearing errors.
    sudo -n journalctl -u iachat --since "@$deploy_started_epoch" --no-pager --output=cat 2>/dev/null |
      grep -oE 'IACHAT_PROVIDER_DIAG provider=(groq|openrouter|nvidia) model=[A-Za-z0-9./:_-]+ status=[A-Za-z0-9_]+' |
      sort | uniq -c | head -40 || true
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
    # systemctl restart can return before Uvicorn binds its socket. Wait for
    # actual readiness instead of declaring rollback broken on the first curl.
    rollback_ready=0
    for attempt in $(seq 1 25); do
      if sudo -n systemctl is-active --quiet iachat && curl -fsS --max-time 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
        rollback_ready=1
        break
      fi
      sleep 1
    done
    if [[ "$rollback_ok" -eq 1 && "$config_restored" -eq 1 && "$rollback_ready" -eq 1 ]]; then
      echo "Rollback health: OK (inference not verified)"
    else
      rollback_incomplete=1
      echo "::error::Rollback health check failed after 25 attempts; manual recovery required."
    fi
  fi
  if [[ "$rollback_incomplete" -eq 1 ]]; then
    # Keep both the previous code and systemd drop-in backup for manual repair.
    # mktemp directories are private; do not print their contents or secrets.
    echo "::error::Rollback incomplete; preserving recovery files: backup=$backup stage=$stage"
  else
    cleanup
  fi
  exit "$status"
}
trap rollback EXIT
test -f "$archive"
test -d "$app/.venv"
test -d "$app/.git"
# Clean code replacement, explicitly approved: production edits are not a release gate.
# Back up the complete existing application code (including modified tracked
# files) BEFORE replacing it. Runtime databases, credentials and venv remain
# excluded from rsync and are never deleted by the deployment.
# The Git checkout itself is not reset, rewritten or removed.
command -v rsync >/dev/null
command -v python3 >/dev/null
tar -xzf "$archive" -C "$stage" --no-same-owner
test -f "$stage/pyproject.toml"
test -f "$stage/iachat/app.py"
# Require the existing rollback script to be present in the release.
test -f "$stage/scripts/rollback_release.py"
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
  "$app/" "$backup/"
# Online SQLite snapshot before additive schema changes. Private and checked.
sudo -n env IACHAT_DB_BACKUP_TARGET="$recovery_dir/database-before.sqlite3" \
  /usr/bin/python3 "$stage/scripts/backup_iachat_db.py"
# Verify Google OAuth credentials privately before any service change.
# The original Google JSON is only used for consistency checks; never copied.
sudo -n python3 - <<'PY'
import json, os, stat
from pathlib import Path
root = Path("/etc/iachat")
json_path, env_path = root / "google-client.json", root / "google-oidc.env"
for path in (json_path, env_path):
    st = path.stat()
    assert stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == 0 and st.st_gid == 0 and st.st_size > 0, "google_credentials_permissions_invalid"
data = json.loads(json_path.read_text())
web = data.get("web")
assert isinstance(web, dict), "google_client_not_web"
env = {}
for raw in env_path.read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    key, sep, value = line.partition("=")
    assert sep, "google_env_format_invalid"
    env[key.strip().removeprefix("export ").strip()] = value.strip().strip('"').strip("'")
assert env.get("IACHAT_GOOGLE_CLIENT_ID") and env.get("IACHAT_GOOGLE_CLIENT_SECRET"), "google_env_values_missing"
assert env.get("IACHAT_PUBLIC_ORIGIN") == "https://ia-chat.duckdns.org", "google_public_origin_invalid"
assert env["IACHAT_GOOGLE_CLIENT_ID"] == web.get("client_id"), "google_client_id_mismatch"
assert env["IACHAT_GOOGLE_CLIENT_SECRET"] == web.get("client_secret"), "google_client_secret_mismatch"
assert "https://ia-chat.duckdns.org/auth/google/callback" in web.get("redirect_uris", []), "google_redirect_mismatch"
print("GOOGLE_OIDC_PREFLIGHT: files present, root 0600, values and redirect consistent (secrets withheld)")
PY
deployed=1
rsync -a --checksum --exclude='.git/' --exclude='.venv/' --exclude='*.db' --exclude='*.db-*' --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
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
printf '[Service]\nEnvironmentFile=%s\nEnvironmentFile=/etc/iachat/google-oidc.env\nEnvironment=IACHAT_BACKEND=integrated\n' "$provider_file" | sudo -n tee "$dropin" >/dev/null
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
# /api/router/status is private by design. Use public /ready for
# integrated-backend configuration; never bypass authentication for a smoke.
code, status = probe("/ready")
assert code == 200 and status.get("mode") == "integrated" and status.get("status") == "ready", "Integrated providers unavailable"
code, _ = probe("/api/router/status")
assert code == 401, "Private router status API not protected"
code, _ = probe("/api/conversations")
assert code == 401, "Private conversations API not protected"
print("Postdeploy: integrated readiness and private API protection OK (inference not verified)")
PY
# Report Google configuration without printing any credentials or claiming consent completed.
"$app/.venv/bin/python" - <<'PY'
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit
base = "http://127.0.0.1:8000"
with urllib.request.urlopen(base + "/auth/status", timeout=5) as response:
    status = json.load(response)
assert status["authenticated"] is False
assert status.get("google_enabled") is True, "google_oidc_not_loaded"
if status.get("google_enabled"):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(base + "/auth/google/start", timeout=5)
        raise AssertionError("google_start_did_not_redirect")
    except urllib.error.HTTPError as exc:
        assert exc.code == 302
        assert urlsplit(exc.headers["Location"]).hostname == "accounts.google.com"
        assert "iachat_google_flow=" in exc.headers.get("Set-Cookie", "")
    print("GOOGLE_OIDC: configured, redirect and state cookie verified; real Google consent not verified")
else:
    print("GOOGLE_OIDC: not configured; Google Client ID/Secret and public origin required")
PY

# Always verify the bytes actually installed, not the dirty Git checkout HEAD.
# Live-provider E2E is explicitly opt-in: 429/503 quota exhaustion on FREE
# providers must not block a release whose deterministic CI and protected HTTP
# health/auth checks passed. This DOES NOT certify live inference.
expected_app_sha256="$(sha256sum "$stage/iachat/app.py" | cut -d ' ' -f 1)"
test "$(sha256sum "$app/iachat/app.py" | cut -d ' ' -f 1)" = "$expected_app_sha256" || {
  echo "::error::Installed app hash does not match release"
  exit 1
}
echo "IAchat release hash: verified"
if [[ "${IACHAT_RUN_LIVE_E2E:-0}" == "1" ]]; then
  sudo -n env IACHAT_E2E_EXPECTED_APP_SHA256="$expected_app_sha256" \
    /usr/bin/python3 "$app/scripts/iachat_production_e2e.py" --launch
  echo "Live free-provider E2E: PASS"
else
  echo "Live free-provider E2E: NOT RUN (separate verification required)"
fi
# The manual recovery job verifies the exact post-release systemd drop-in
# before restoring it. This marker is private and never printed in logs.
sudo -n sha256sum "$dropin" | awk '{print $1}' > "$stage/.dropin-deployed-sha256"
deployed=0
echo "IAchat deployed successfully (HTTP/auth/CI verified; live inference NOT verified unless explicitly run)"
