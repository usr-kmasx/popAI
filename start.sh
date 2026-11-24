#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Use the project-local Python installed by install.sh, if available.
if [[ -x "$ROOT/tools/local/venv/bin/python" ]]; then
  exec "$ROOT/tools/local/venv/bin/python" "$ROOT/server.py" "$@"
fi
exec python3 "$ROOT/server.py" "$@"
