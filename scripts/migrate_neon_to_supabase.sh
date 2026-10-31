#!/usr/bin/env bash
# scripts/migrate_neon_to_supabase.sh
# Migrates data-only from Neon Postgres to Supabase Postgres.
#
# Usage:
#   NEON_URL="postgresql://..." SUPABASE_URL="postgresql://..." ./scripts/migrate_neon_to_supabase.sh
#
# Requirements:
#   - pg_dump and psql installed (postgresql-client)
#   - Both databases reachable and Supabase migrations already applied (alembic upgrade head)

set -euo pipefail

if [ -z "${NEON_URL:-}" ] || [ -z "${SUPABASE_URL:-}" ]; then
    echo "ERROR: Both NEON_URL and SUPABASE_URL must be set."
    echo "Example: NEON_URL='postgresql://...' SUPABASE_URL='postgresql://...' $0"
    exit 1
fi

echo "================================================================="
echo "WARNING: This will copy data from Neon Postgres to Supabase Postgres."
echo "Supabase tables will receive migrated rows."
echo "================================================================="
read -r -p "Are you sure you want to proceed? [y/N] " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted by user."
    exit 0
fi

echo ">> Starting data migration..."
pg_dump --data-only --no-owner --no-privileges "$NEON_URL" | psql "$SUPABASE_URL"

echo ">> Data migration completed successfully."
