#!/bin/bash
# startup.sh — bootstrap local development dependencies and services.
# Idempotent: safe to run multiple times.

set -euo pipefail
cd "$(dirname "$0")"

echo "==> Music Analysis Platform Local Setup"

# 1. Check Python
PY=python3
echo ">> Using Python: $("$PY" --version)"

# 2. Install dependencies
echo ">> Installing API dependencies..."
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements.txt

# 3. Start local Postgres + Redis if Docker is present
if command -v docker >/dev/null 2>&1; then
    echo ">> Starting local Postgres and Redis via docker compose..."
    docker compose -f docker-compose.dev.yml up -d
fi

# 4. Alembic migrations if DATABASE_URL is set
if [ -n "${DATABASE_URL:-}" ]; then
    echo ">> Applying Alembic migrations..."
    "$PY" -m alembic upgrade head
else
    echo ">> No DATABASE_URL set. To run migrations: export DATABASE_URL='...' && alembic upgrade head"
fi

echo "==> Setup complete."
