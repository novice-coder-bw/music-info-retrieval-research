#!/usr/bin/env bash
# deploy/release.sh
# Zero-downtime release script executed on the Droplet over SSH.
#
# NOTE: Database migrations are additive (expand/contract).
# Migrations are NOT rolled back if deployment fails, ensuring the
# previous image can safely continue functioning.

set -euo pipefail

cd /opt/mir

NEW_TAG="${1:-}"
if [ -z "$NEW_TAG" ]; then
    echo "ERROR: New TAG parameter required (e.g., ./release.sh <tag>)"
    exit 1
fi

if [ -f /opt/mir/.env ]; then
    # shellcheck disable=SC1091
    source /opt/mir/.env
else
    echo "ERROR: /opt/mir/.env not found."
    exit 1
fi

PREV_TAG=""
if [ -f /opt/mir/.tag ]; then
    PREV_TAG=$(cat /opt/mir/.tag)
fi

echo ">> Starting release for TAG=$NEW_TAG (Previous TAG=$PREV_TAG)"
export TAG="$NEW_TAG"

echo ">> Pulling container images..."
docker compose pull api worker

echo ">> Running database migrations (alembic upgrade head)..."
# Additive migrations only; not rolled back on container failure
docker compose run --rm api alembic upgrade head

echo ">> Starting new containers..."
docker compose up -d --remove-orphans

echo ">> Verifying health check at https://${DOMAIN}/health (up to 100s)..."
HEALTH_OK=0
for i in $(seq 1 20); do
    if curl -fsS "https://${DOMAIN}/health" >/dev/null 2>&1; then
        echo ">> Health check passed on attempt $i."
        HEALTH_OK=1
        break
    fi
    echo ">> Waiting for healthy service (attempt $i/20)..."
    sleep 5
done

if [ "$HEALTH_OK" -eq 1 ]; then
    echo "$NEW_TAG" > /opt/mir/.tag
    echo ">> Release succeeded! Current tag: $NEW_TAG"
    exit 0
else
    echo "::error::Health check failed after 100 seconds! Rolling back to PREV_TAG=$PREV_TAG"
    if [ -n "$PREV_TAG" ]; then
        export TAG="$PREV_TAG"
        docker compose up -d --remove-orphans
        echo "$PREV_TAG" > /opt/mir/.tag
        echo ">> Rollback completed."
    else
        echo ">> No previous tag recorded; cannot restore earlier containers."
    fi
    exit 1
fi
