#!/bin/bash
# run_all.sh — run API and Celery worker locally for development.

set -uo pipefail
cd "$(dirname "$0")"

PY=python3

echo "==> Starting API..."
"$PY" -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "==> Starting Celery worker..."
"$PY" -m celery -A workers.tasks worker --loglevel=info -c 1 &
CELERY_PID=$!

echo "==> Stack running: backend=$BACKEND_PID worker=$CELERY_PID"
echo "    API: http://localhost:8000"
echo "    Health: http://localhost:8000/health"
echo "    Press Ctrl-C to stop."

cleanup() {
    echo "==> Stopping services..."
    kill "$CELERY_PID" 2>/dev/null || true
    kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait
