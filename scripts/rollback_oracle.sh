#!/usr/bin/env bash
# Explicitly authorized rollback of the latest IAchat code release on Oracle.
# Never called automatically; GitHub Actions protects this with oracle-production.
set -Eeuo pipefail
run_id="${1:?missing_release_run_id}"
[[ "$run_id" =~ ^[1-9][0-9]{5,17}$ ]] || { echo 'invalid_release_run_id'; exit 2; }
app="$HOME/Proyecto/Aplicaciones/IAchat"
recovery_base="$HOME/.local/state/iachat-releases"
shopt -s nullglob
matches=("$recovery_base/${run_id}."*)
[[ ${#matches[@]} -eq 1 && -d "${matches[0]}" ]] || { echo 'release_snapshot_not_unique_or_missing'; exit 2; }
recovery_dir="${matches[0]}"
stage="$recovery_dir/stage"
backup="$recovery_dir/backup"
[[ -d "$stage" && -d "$backup" && -d "$app/.git" && -d "$app/.venv" ]] || { echo 'release_snapshot_incomplete'; exit 2; }
# Only the newest successful release can be rolled back. A later release
# requires its own snapshot; never restore older code over newer deployments.
for candidate in "$recovery_base"/[0-9]*.*; do
  [[ -d "$candidate" ]] || continue
  other="${candidate##*/}"
  other="${other%%.*}"
  if [[ "$other" =~ ^[0-9]{6,18}$ ]] && (( 10#$other > 10#$run_id )); then
    echo 'newer_release_snapshot_exists'; exit 2
  fi
done
# Refuse to overwrite code that changed since deployment. rsync output is
# intentionally captured, not printed: it can include private file names.
exclude=(--exclude='.git/' --exclude='.venv/' --exclude='*.db' --exclude='*.db-*' \
         --exclude='*.sqlite' --exclude='*.sqlite-*' --exclude='*.sqlite3' \
         --exclude='*.sqlite3-*' --exclude='.env' --exclude='.env.*' \
         --exclude='.dropin-deployed-sha256')
drift="$(rsync -a -n --checksum --itemize-changes "${exclude[@]}" "$stage/" "$app/")"
[[ -z "$drift" ]] || { echo 'deployed_code_has_drift_manual_review_required'; exit 2; }
dropin='/etc/systemd/system/iachat.service.d/20-integrated-providers.conf'
expected_hash_file="$stage/.dropin-deployed-sha256"
[[ -f "$expected_hash_file" ]] || { echo 'missing_dropin_integrity_marker'; exit 2; }
expected_hash="$(cat "$expected_hash_file")"
[[ "$expected_hash" =~ ^[a-f0-9]{64}$ ]] || { echo 'invalid_dropin_integrity_marker'; exit 2; }
actual_hash="$(sudo -n sha256sum "$dropin" | awk '{print $1}')"
[[ "$actual_hash" == "$expected_hash" ]] || { echo 'systemd_configuration_has_drift'; exit 2; }
# The previous release backup is private and excludes credentials, databases
# and virtualenv. Do not delete recovery files: keep them for incident review.
python3 "$stage/scripts/rollback_release.py" "$stage" "$backup" "$app"
rsync -a --checksum "${exclude[@]}" "$backup/" "$app/"
"$app/.venv/bin/python" -m pip install -e "$app" --disable-pip-version-check -q
previous_dropin="$stage/.env.iachat-systemd-rollback"
if [[ -f "$previous_dropin" ]]; then
  sudo -n cp -p "$previous_dropin" "$dropin"
else
  sudo -n rm -f "$dropin"
fi
sudo -n systemctl daemon-reload
sudo -n systemctl restart iachat
sudo -n systemctl is-active --quiet iachat
curl -fsS --max-time 10 http://127.0.0.1:8000/health >/dev/null
printf 'Authorized rollback complete: release_run_id=%s; health=ok; live_inference=not_verified\n' "$run_id"
