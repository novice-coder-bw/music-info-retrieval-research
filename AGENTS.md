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

# Agent guide (maintained by hand, outside the managed block)

Read `README.md` first for the architecture, API and configuration. This file says how to work in the repo without breaking it.

## System in one minute

- **API**: FastAPI (`backend/app/main.py`, auth in `backend/app/auth.py`), live at `https://mirr-web.duckdns.org`. Every route except `GET /health` needs a Supabase JWT.
- **Worker**: Celery tasks in `workers/tasks.py` (analysis and Demucs separation). Redis is the broker.
- **Data**: SQLAlchemy models in `db/models.py`, queries in `db/store.py`, engine in `db/engine.py`, migrations in `alembic/versions/`. Supabase Postgres via the session pooler.
- **Storage**: `services/storage.py` (Cloudflare R2 through boto3; presigned PUT and GET).
- **Schemas**: `shared/schemas.py` (Pydantic request/response models, the API contract).
- **Deploy**: `deploy/` (Dockerfiles, Compose, Caddyfile, `release.sh`, `cloud-init.yaml`) and `.github/workflows/`. Runs on a DigitalOcean Droplet.
- **Frontend**: separate repo `novice-coder-bw/mirr-web` (Cloudflare Workers, also edited with Lovable). It consumes this repo's `/openapi.json`.

## You cannot reach production

You have no credentials and cannot call Supabase, R2, the Droplet or DigitalOcean. Work only through code and pull requests, and say in the PR what you could not verify (live upload, real database, a real Demucs run). Never run `scripts/migrate_neon_to_supabase.sh`. Never merge your own PR. Never rewrite published git history.

## Rules by area

### Database and migrations
- One new Alembic revision per model change. Never edit an applied revision. Keep migrations additive (add, backfill, switch, drop later) because the previous image must keep working after a deploy; migrations are not rolled back.
- Guard Supabase-only SQL (`auth.uid()`, publications) with an `auth` schema existence check so CI on plain Postgres still passes.
- `alembic upgrade head` and `alembic check` must both pass.
- Use the `postgresql+psycopg://` driver. The API connects as the `postgres` role, which bypasses RLS, so enforce ownership (`user_id`) in application code and keep RLS enabled on every new `public` table.
- Never create tables or schema through Supabase, Lovable or edge functions.

### Storage
- R2 only. Required variables fail fast; do not add silent fallbacks. Clients receive presigned URLs; do not make the bucket public or set `R2_PUBLIC_BASE_URL` without the owner's explicit request.

### Auth and security
- Every route except `/health` (and FastAPI's `/docs`, `/redoc`, `/openapi.json`) must depend on `get_current_user_id`. No auth bypass flags or debug backdoors. Tests use `app.dependency_overrides`.
- Check ownership on every session or upload-intent lookup, and **fail closed**: a record with no `user_id` is not owned by the caller. (Current code is fail-open for legacy rows with `user_id` NULL; see "Known limitations" in `README.md`. New code must not copy that pattern.)
- Derive R2 object keys from server-side records (session, upload intent), never from client-supplied URLs or keys. Verify uploaded objects from R2 (`head_object`); never trust client-supplied size or type.
- Do not log tokens, database URLs or presigned URLs.

### API and contract
- Change the API additively under `/api/v1`; give new routes an explicit `response_model` and documented error responses. Do not rename or remove fields, and do not add stage status values. Stages use `pending | active | completed | failed`.
- A breaking change needs a new version (`/api/v2`) or an owner-approved migration plan with a matching `mirr-web` change.
- The legacy unversioned `/api/*` aliases are deprecated; do not add new ones.

### Workers and ML
- `ALLOW_PLACEHOLDER_STEMS` is `1` only in CI and tests; production must fail loudly. Delete temporary files after uploading results to R2. The production worker runs with concurrency 1.

### Docker and deploy files
- `deploy/worker.Dockerfile` copies `requirements.txt` **and** `requirements-worker.txt` (the second includes the first). Keep both Dockerfiles building: CI builds them on every PR.
- Only Caddy publishes ports (80/443). Redis and the API are never exposed. Do not remove `release.sh`'s health check or rollback.
- Values in `/opt/mir/.env` must be single-quoted because `release.sh` reads the file with bash.

### GitHub Actions
- The repo is public, so logs are public: never print secrets, IP addresses or database URLs, and pass workflow inputs through `env:` instead of interpolating `${{ inputs.* }}` inside `run:` scripts.
- Pin actions to a major version, use minimal `permissions`, and keep the `production` environment (owner approval) on anything that deploys or uses deploy secrets.
- A `workflow_dispatch` workflow only appears in the Actions tab when it exists on the default branch.
- Do not edit `provision-droplet.yml` or `cloud-init.yaml` unless asked. There is no DigitalOcean access from here.
- Do not add `[skip ci]` to commits that open or update pull requests; it also skips pull-request checks.

### Secrets and configuration
- Placeholders only, in `.env.example`, docs and tests. Required GitHub secrets and the Droplet `.env` are listed in `docs/RUNBOOK.md`.

## Playbooks

**Add or change an endpoint**
1. Add or update Pydantic models in `shared/schemas.py` and the route in `backend/app/main.py` under `/api/v1`, with `Depends(get_current_user_id)` and ownership checks.
2. Add tests in `backend/app/test_main.py` for success, 401, ownership failure and validation errors.
3. Run `python scripts/export_openapi.py` to confirm the contract still builds without a database.
4. Describe the contract change in the PR; the deploy workflow syncs `openapi.json` to `mirr-web`.

**Change a model**
1. Edit `db/models.py`, add the next Alembic revision (additive, Supabase-only SQL guarded), enable RLS on any new table.
2. Run `alembic upgrade head` and `alembic check` against a local Postgres; update `db/store.py` and tests.

**Add an environment variable**
1. Read it in code with a clear failure if required. Add it to `.env.example` (placeholder), the table in `README.md` and `docs/RUNBOOK.md`, and the Compose `env_file` flow if the container needs it. Tell the owner which secret or `.env` line to create; do not invent values.

**Change a workflow or deploy file**
1. Keep changes minimal and explain how you validated them (for example `docker compose config`, `actionlint`). Deploys are triggered by pushes to `main` that touch the path filter in `deploy-backend.yml`.

## Verification checklist (before opening a PR)

```bash
ruff check .          # py312, line length 120, rules E/F/W
alembic upgrade head && alembic check
pytest                # needs Postgres (DATABASE_URL); CI uses CELERY_EAGER=1 and ALLOW_PLACEHOLDER_STEMS=1
docker build -f deploy/api.Dockerfile .      # when requirements or Dockerfiles changed
docker build -f deploy/worker.Dockerfile .
```

## Working with the frontend repo

`mirr-web` generates TypeScript types from this API's `openapi.json` and maps backend statuses to its own UI states. It is also edited with Lovable, so API changes must be additive and documented. The API's allowed origins come from `CORS_ORIGIN_REGEX` (an ops setting on the Droplet); if a feature needs a new frontend origin, document it in `docs/RUNBOOK.md` and tell the owner.

## Pull request conventions

- One concern per PR, conventional commit titles (`feat:`, `fix:`, `docs:`, `chore:`). Branch from `main` and open the PR against `main` unless told otherwise.
- The description lists what changed, how you tested it, anything you could not verify, and any manual step for the owner (secrets, `.env`, dashboards).
- Keep CI green. Do not merge.

## Documentation hierarchy and areas to ignore

- Authoritative: `README.md`, this file, `docs/RUNBOOK.md`, `docs/FREE_TIER_LIMITS.md`, `docs/R2_CORS.md`.
- Historical and possibly outdated: `techstack.md`, `environments.md`, `Music-Analysis-Platform.md`, `implementation-alignment-report.md`, `BMAD_ORIENTATION.md`. When they conflict with the authoritative files, ignore them.
- Tooling you should not modify unless asked: `_bmad/`, `.agent/`, `.agents/`, `.kiro/`, `skills-lock.json`, `docs/agents/`.
- `frontend/` is a legacy Next.js app and is unused; do not build features there.
