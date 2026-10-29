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
# Run the diagnostic code over SSH stdin; no script, keys, or logs are written to Oracle.
# The remote script prints only allowlisted status fields and aggregated log signals.
ssh -i "$keyfile" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$knownfile" -o ConnectTimeout=15 "$ORACLE_USER@$ORACLE_HOST" 'python3 -' < scripts/iachat_remote_diagnostics.py
