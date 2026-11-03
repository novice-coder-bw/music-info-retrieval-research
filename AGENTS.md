<!-- bmad:context -->
<!-- Verified 2026-08-14 against 7eb0e67. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## Music Analysis Platform

MIR platform for stem separation. FastAPI, SQLAlchemy/Alembic, Celery/Redis, Supabase Postgres, and Cloudflare R2.

## Policy & Standing Rules

- **Postgres (Supabase) only**: No SQLite and no local storage fallbacks in any code path.
- **Durable object storage (Cloudflare R2 only)**: S3-compatible storage via boto3; no local upload fallbacks.
- **Alembic migrations**:
  - Every model change requires a new Alembic revision.
  - Applied revisions are NEVER edited.
  - Migrations must be strictly additive (expand/contract) so older container images keep working during rolling releases.
- **Pre-PR checks**: Always run `ruff check .` and `pytest` before opening any PR.
- **Never commit secrets**: Use environment variable placeholders only.
- **API evolution**: The public API is strictly additive under `/api/v1` (with `/api/*` retained as deprecated aliases).

## Running and verifying

- Backend tests: `pytest`
- Linting: `ruff check .`
- Migrations: `alembic check` / `alembic upgrade head`

<!-- /bmad:context -->
