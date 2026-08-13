#!/bin/bash
# run_all.sh — run the full Music Analysis Platform stack.
#
# Starts the FastAPI backend, the Celery worker, and the Next.js frontend
# concurrently. Ctrl-C (or otherwise exiting) stops all spawned jobs.
#
# NOTE: Uses the active Python (the Studio's default conda env) because Studio
# forbids creating virtualenvs. If a backend/venv already exists, it is used.
# The Celery worker is started only if Celery is importable in that Python.
set -uo pipefail
cd "$(dirname "$0")"

# Choose the Python interpreter (same rule as startup.sh).
PY="backend/venv/bin/python"
if [ ! -x "$PY" ]; then
    PY=python3
fi

# --- Backend (FastAPI) -------------------------------------------------------
(
    cd backend
    exec "$PY" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# --- Celery worker (optional) ------------------------------------------------
CELERY_PID=""
if "$PY" -c "import celery" 2>/dev/null; then
    # workers.tasks lives at the repo root, so run from the root directory.
    "$PY" -m celery -A workers.tasks worker --loglevel=info &
    CELERY_PID=$!
else
    echo "!! Celery not available — skipping worker (re-run ./startup.sh to install backend deps)."
fi

# --- Frontend (Next.js) ------------------------------------------------------
(
    cd frontend
    exec npm run dev
) &
FRONTEND_PID=$!

echo "==> Stack running: backend=$BACKEND_PID frontend=$FRONTEND_PID celery=${CELERY_PID:-n/a}"
echo "    Backend:  http://localhost:8000"
echo "    Frontend: http://localhost:3000"
echo "    Press Ctrl-C to stop everything."

cleanup() {
    echo "==> Stopping all services..."
    [ -n "$CELERY_PID" ] && kill "$CELERY_PID" 2>/dev/null
    kill "$FRONTEND_PID" 2>/dev/null
    kill "$BACKEND_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

# Wait for any background job to finish (e.g. Ctrl-C terminates a child).
wait
