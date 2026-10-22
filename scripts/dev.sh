#!/usr/bin/env bash
# Development: backend on :8000 (auto-reload) + Vite on :5173 (proxy to /api).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  "$PYTHON" -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT

PYTHONPATH=backend ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
(cd frontend && npm run dev)

wait
