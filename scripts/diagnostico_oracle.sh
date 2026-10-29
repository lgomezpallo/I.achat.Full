#!/usr/bin/env bash
set -euo pipefail
test -n "${ORACLE_HOST:-}"
test -n "${ORACLE_USER:-}"
test -n "${ORACLE_SSH_KEY:-}"
install -d -m 700 "$HOME/.ssh"
keyfile="$(mktemp "$HOME/.ssh/oracle-key.XXXXXX")"
knownfile="$(mktemp "$HOME/.ssh/oracle-known.XXXXXX")"
trap 'rm -f "$keyfile" "$knownfile"' EXIT
printf '%s\n' "$ORACLE_SSH_KEY" > "$keyfile"
chmod 600 "$keyfile"
ssh-keyscan -T 10 -t ed25519 "$ORACLE_HOST" 2>/dev/null > "$knownfile"
actual="$(ssh-keygen -lf "$knownfile" -E sha256 | awk '{print $2}' | head -1)"
test "$actual" = 'SHA256:JCUGOZrLtlE+FkPv+evyeSAdxDs5iYqLk7hteTpOBHI'
ssh -i "$keyfile" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$knownfile" -o ConnectTimeout=15 "$ORACLE_USER@$ORACLE_HOST" 'set -e; printf "iachat_service: "; systemctl is-active iachat; printf "router_service: "; systemctl is-active router; printf "iachat_health: "; curl -fsS --max-time 5 http://127.0.0.1:8000/health; printf "\nrouter_health: "; curl -fsS --max-time 5 http://127.0.0.1:8010/health; printf "\n"; repo=/home/ubuntu/Proyecto/Aplicaciones/IAchat; if test -d "$repo/.git"; then printf "iachat_revision: "; git -C "$repo" rev-parse --short HEAD; printf "iachat_branch: "; git -C "$repo" branch --show-current; printf "iachat_modified_count: "; git -C "$repo" status --porcelain --untracked-files=no | wc -l; else echo "iachat_revision: repo_not_found"; fi; if test -d "$repo/.git"; then printf "iachat_source_modified_paths:\n"; git -C "$repo" status --porcelain --untracked-files=no | cut -c4- | grep -E "^(iachat|scripts)/[A-Za-z0-9_/-]+\.(py|sh)$" || true; for module in web_planner.py web_research.py web_search.py app.py backend.py; do if test -f "$repo/iachat/$module"; then printf "iachat_module_%s_sha256: " "$module"; sha256sum "$repo/iachat/$module" | cut -d " " -f 1; else printf "iachat_module_%s_sha256: absent\n" "$module"; fi; done; fi'
