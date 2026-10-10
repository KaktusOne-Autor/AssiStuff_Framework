#!/usr/bin/env zsh
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    exec "$PROJECT_ROOT/.venv/bin/python" -m assistuff "$@"
fi
exec python3 -m assistuff "$@"