#!/usr/bin/env bash
# Run on Oracle with an existing Router runtime environment.
# Does not restart services or access production conversation SQLite.
set -euo pipefail
test "$IACHAT_SMOKE_LIVE" = 1 || { echo 'Explicit live opt-in required'; exit 2; }
test -n "$ROUTER_URL" && test -n "$ROUTER_TOKEN" || { echo 'Router environment unavailable'; exit 2; }
python scripts/smoke_conversation.py
