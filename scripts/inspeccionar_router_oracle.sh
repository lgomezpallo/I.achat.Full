#!/usr/bin/env bash
set -euo pipefail
test -n "${ORACLE_HOST:-}" && test -n "${ORACLE_USER:-}" && test -n "${ORACLE_SSH_KEY:-}"
install -d -m 700 "$HOME/.ssh"
keyfile="$(mktemp "$HOME/.ssh/router-key.XXXXXX")"
knownfile="$(mktemp "$HOME/.ssh/router-known.XXXXXX")"
trap 'rm -f "$keyfile" "$knownfile"' EXIT
printf '%s\n' "$ORACLE_SSH_KEY" > "$keyfile"
chmod 600 "$keyfile"
ssh-keyscan -T 10 -t ed25519 "$ORACLE_HOST" 2>/dev/null > "$knownfile"
actual="$(ssh-keygen -lf "$knownfile" -E sha256 | awk '{print $2}' | head -1)"
test "$actual" = 'SHA256:JCUGOZrLtlE+FkPv+evyeSAdxDs5iYqLk7hteTpOBHI'
ssh -i "$keyfile" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$knownfile" -o ConnectTimeout=15 "$ORACLE_USER@$ORACLE_HOST" 'bash -s' <<'REMOTE'
set -euo pipefail
printf 'router_active: '; systemctl is-active router
printf 'router_unit: '; systemctl show router -p FragmentPath --value
printf 'router_workdir: '; systemctl show router -p WorkingDirectory --value
printf 'router_user: '; systemctl show router -p User --value
printf 'router_exec: '; systemctl show router -p ExecStart --value
printf 'router_health: '; curl -fsS --max-time 5 http://127.0.0.1:8010/health | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "unknown"))'
app=/home/ubuntu/Proyecto/Herramientas/Router
if test -d "$app"; then
  echo 'router_dir: present'
  if test -d "$app/.git"; then
    printf 'router_commit: '; git -C "$app" rev-parse HEAD
    printf 'router_branch: '; git -C "$app" branch --show-current
    printf 'router_dirty: '; if test -n "$(git -C "$app" status --porcelain)"; then echo yes; else echo no; fi
  else
    echo 'router_git: absent'
  fi
  printf 'router_venv: '; if test -x "$app/.venv/bin/python"; then echo present; else echo absent; fi
else
  echo 'router_dir: absent'
fi
REMOTE
