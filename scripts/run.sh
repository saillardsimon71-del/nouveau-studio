#!/usr/bin/env bash
# Production-ish single process: builds the UI once, then serves API + UI + media.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

exec env PYTHONPATH=backend ./.venv/bin/uvicorn app.main:app \
  --host "${PVS_HOST:-0.0.0.0}" --port "${PVS_PORT:-8000}" --workers 1
