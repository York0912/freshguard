#!/bin/bash
# freshguard.sh — Shell freshness gate
# Usage: ./freshguard.sh --hours 48 --min 2 -- python3 search.py
# The command must emit FreshGuard JSON. Do not use this wrapper to parse HTML.
# Returns: 0 (proceed) or 1 (silent/error)

set -euo pipefail

HOURS=48
MIN=2
CMD=()
PYTHON_BIN="${FRESHGUARD_PYTHON:-python3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours) HOURS="$2"; shift 2 ;;
    --min) MIN="$2"; shift 2 ;;
    --) shift; CMD=("$@"); break ;;
    *) echo "Usage: $0 --hours N --min N -- command [args...]"; exit 1 ;;
  esac
done

if [[ ${#CMD[@]} -eq 0 ]]; then
  echo "Usage: $0 --hours N --min N -- command [args...]"
  exit 1
fi

RESULTS=$("${CMD[@]}" 2>/dev/null) || {
  echo "SEARCH_ERROR: search command failed"
  exit 1
}

# Count the explicit freshness flags from trusted JSON stdin. Keeping search
# output out of the Python source prevents a result containing quotes from
# becoming executable Python code.
FRESH_COUNT=$(printf '%s' "$RESULTS" | "$PYTHON_BIN" -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
    items = payload.get("items", [])
    print(sum(item.get("fresh") is True for item in items))
except (json.JSONDecodeError, AttributeError):
    print(0)
')

if [[ "$FRESH_COUNT" -ge "$MIN" ]]; then
  echo "$RESULTS"
  exit 0
else
  echo "NO_NEW_CONTENT"
  exit 0
fi
