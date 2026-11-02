#!/bin/bash
# startup.sh — bootstrap the Music Analysis Platform environment.
#
# Run manually (or via Studio startup settings) after every Studio boot to
# re-initialize dependencies and background services. Idempotent: safe to run
# multiple times.
#
# IMPORTANT (Lightning AI Studio): Studio does NOT allow creating virtualenvs —
# a Studio has a single default conda environment (max 1 environment). So this
# script installs dependencies into that default Python, NOT a fresh backend/venv.
# If a backend/venv already happens to exist (e.g. on a non-Studio host), it is
# used in preference.
#
# Persistence notes (see STUDIO_SETUP.md):
#  - Dependencies are installed into the Studio's default conda env, which is
#    re-created/persisted by Studio, not by us.
#  - frontend/node_modules persists inside the repo.
#  - Redis DATA persists via the ./redis-data Docker volume; only the container
#    needs (re)starting after a boot.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Music Analysis Platform startup"

# 1. Choose the Python interpreter.
#    Prefer an existing backend/venv; otherwise use the active Python (the
#    Studio's default conda env) because Studio forbids creating new venvs.
PY="backend/venv/bin/python"
if [ ! -x "$PY" ]; then
    PY=python3
fi
echo ">> Using Python: $("$PY" --version) @ $("$PY" -c 'import sys; print(sys.executable)')"

# 2. Backend dependencies (into the chosen environment).
echo ">> Installing/updating backend dependencies..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r backend/requirements.txt

# 3. Frontend dependencies
if [ ! -d "frontend/node_modules" ]; then
    echo ">> Installing frontend dependencies..."
    (cd frontend && npm install)
else
    echo ">> frontend/node_modules already present (skipping npm install)."
fi

# 4. Redis via Docker (data persists in ./redis-data)
echo ">> Ensuring Redis container is running..."
if docker ps -a -q -f name=music-redis | grep -q .; then
    docker start music-redis
else
    mkdir -p redis-data
    docker run --name music-redis -p 6379:6379 -d \
        -v "$(pwd)/redis-data:/data" \
        redis:latest redis-server --appendonly yes
fi

# 5. Apply database migrations if a DATABASE_URL is configured
if grep -q '^DATABASE_URL=' .env 2>/dev/null && [ -n "$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" ]; then
    echo ">> Applying Alembic migrations..."
    "$PY" -m alembic upgrade head
else
    echo ">> No DATABASE_URL set — skipping migrations. See .env.example."
fi

echo "==> Environment setup complete."
