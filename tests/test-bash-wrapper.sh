#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

output="$(bash "$ROOT/reference/bash/freshguard.sh" --hours 48 --min 1 -- python3 -c 'import json; print(json.dumps({"items": [{"fresh": True}]}))')"
[[ "$output" == *'"fresh": true'* ]]

if bash "$ROOT/reference/bash/freshguard.sh" --cmd 'echo unsafe' >/dev/null 2>&1; then
  echo 'FAIL legacy string command was accepted'
  exit 1
fi

echo 'PASS bash wrapper executes argument arrays and rejects string commands'
