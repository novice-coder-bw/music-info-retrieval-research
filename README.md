# Music Analysis Platform (mirr)

A FastAPI + Celery backend for music information retrieval: upload a track, analyze it (BPM, key, structure) and separate it into four stems (`drums`, `bass`, `other`, `vocals`) with Demucs.

| What | Where |
| :--- | :--- |
| API (production) | `https://mirr-web.duckdns.org` — `GET /health` is public; interactive docs at `/docs`; contract at `/openapi.json` |
| Frontend "Stemlab" | `https://mirr-web.novice-coder.workers.dev` — repo [`novice-coder-bw/mirr-web`](https://github.com/novice-coder-bw/mirr-web) |
| Database / Auth | Supabase project `mirr-web` (ref `mghlumhhbjfeqvnmqrjs`, eu-west-3, Postgres 17) |
| Object storage | Cloudflare R2 bucket `music-info-retrieval-research-1` |
| Compute | DigitalOcean Droplet `mirr-server` (Docker Compose: Caddy, API, Celery worker, Redis) |

This repository is **public**. Never commit secrets, and remember GitHub Actions logs are public too.

## Architecture

```
Browser (mirr-web, Cloudflare Workers)
   │ Supabase Auth → JWT              │ presigned PUT / GET (direct to R2)
   ▼                                  ▼
 Caddy ─▶ FastAPI (api) ─ Celery ─ Redis        Cloudflare R2
              │              │
              └── Supabase Postgres (session pooler) ◀┘
 (Caddy, api, worker, redis run on one Droplet via Docker Compose)
```

### Request flow: upload → analyze → separate

1. The frontend signs in with Supabase Auth and sends `Authorization: Bearer <access token>` on every API call.
2. `POST /api/v1/uploads/presign` validates type (`audio/wav`, `audio/mpeg`) and size (`MAX_UPLOAD_MB`), records an upload intent (owner, expected type and size) and returns a presigned R2 PUT URL.
3. The browser uploads the file straight to R2 (the bucket needs CORS for the frontend origin, see `docs/R2_CORS.md`).
4. `POST /api/v1/uploads/complete` checks the intent belongs to the caller and was not used before, verifies the real object in R2 (`head_object` size and content type, deleting invalid objects), creates the session and enqueues analysis. It returns `{file_id, status: "enqueued", artifact_url}`.
5. The Celery worker runs analysis and updates the session's stage status in Postgres.
6. `POST /api/v1/separate` enqueues Demucs; stems are written to R2 and listed on the session.
7. The frontend polls `GET /api/v1/session/{file_id}` for progress and stem URLs.

## API

All routes except `GET /health` require a valid Supabase JWT (RS256/ES256, audience `authenticated`, verified against the project's JWKS). Users can only access their own sessions. FastAPI also serves `/docs`, `/redoc` and `/openapi.json` publicly.

| Route | Purpose |
| :--- | :--- |
| `GET /health` | Public. Booleans only: `status`, `database`, `redis`, `storage`, `worker`; `503`/`degraded` if a check fails. Also keeps the free Supabase project awake via the keepalive workflow. |
| `POST /api/v1/uploads/presign` | Presigned R2 PUT URL for a direct browser upload |
| `POST /api/v1/uploads/complete` | Finalize upload, create session, enqueue analysis |
| `POST /api/v1/upload` | Multipart upload through the API |
| `GET /api/v1/session/{file_id}` | Session, stage statuses, analysis result, stems |
| `POST /api/v1/analyze` | Enqueue analysis |
| `POST /api/v1/separate` | Enqueue 4-stem separation |

Deprecated unversioned aliases that share the same handlers (and the same auth): `POST /api/upload`, `GET /api/session/{file_id}`, `POST /api/analyze`, `POST /api/separate`. They are being phased out; new code must use `/api/v1`.

**Status vocabulary (stable contract):** every stage (`analysis`, `separation`, each entry of `workflow_stages`) uses `pending | active | completed | failed`. The frontend translates these for its UI (`pending`→queued, `active`→processing). Adding a value is a breaking change for the frontend, so coordinate it with `mirr-web`.

Stem and audio URLs returned to clients are short-lived presigned R2 GET URLs unless `R2_PUBLIC_BASE_URL` is set (leave it unset to keep audio private).

## Data model (Supabase Postgres, `public` schema)

Schema is owned by **Alembic** in this repo (`alembic/versions/`, currently `0001`–`0004`). Nothing else may create or alter tables, including Supabase's dashboard, Lovable or edge functions.

| Table | Purpose |
| :--- | :--- |
| `sessions` | One per uploaded track: `file_id` (PK), `user_id`, file metadata, JSON `analysis`, `stems`, `workflow_stages`, timestamps |
| `upload_intents` | Issued presigned uploads (`object_key` PK, owner, expected type/size, `completed`) used to stop hijack and replay |
| `artifacts` | Stored audio and stem objects (key, size, mime type, URL) |

Row Level Security is enabled on these tables (Supabase exposes `public` through its REST API). `sessions` has an `owner_read` SELECT policy (`user_id = auth.uid()`) and is added to the `supabase_realtime` publication. **The API connects as the `postgres` role, which bypasses RLS, so ownership checks in application code are the real access control.** The `alembic_version` table is not yet covered by RLS (planned).

## Configuration

Production settings live in `/mnt/mirr-volume/.env` on the Droplet (never in git; deploys preserve it or sync safely via Base64). `.env.example` lists every variable with placeholders.

| Variable | Notes |
| :--- | :--- |
| `DATABASE_URL` | Required. Supabase **session pooler** (port 5432), format `postgresql+psycopg://postgres.<ref>:<password>@<pooler-host>:5432/postgres`. Fails fast if missing or SQLite. |
| `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Required. Storage fails fast if any are missing. |
| `REDIS_URL` | `redis://redis:6379/0` in Compose, `redis://localhost:6379/0` locally. |
| `DOMAIN` | Required on the Droplet (Caddy TLS and the health check). `TAG` is set by `release.sh`; do not set it by hand. |
| `SUPABASE_JWKS_URL` | Optional; defaults to the project's JWKS URL (`SUPABASE_PROJECT_REF`). |
| `CORS_ORIGIN_REGEX` | Regex of allowed frontend origins (production Workers origin, Cloudflare preview URLs, Lovable preview). |
| `MAX_UPLOAD_MB` | Upload limit, default `100`. |
| `ALLOW_PLACEHOLDER_STEMS` | `0` in production so separation fails loudly; `1` only in CI/tests. |
| `SCRATCH_DIR`, `R2_PUBLIC_BASE_URL`, `CELERY_EAGER` | Optional. `CELERY_EAGER` is for tests only. |

Rules that have caused real failures:

- **Single-quote every value** in `/mnt/mirr-volume/.env` (for example `CORS_ORIGIN_REGEX='^https:\/\/...$'`). `release.sh` parses `DOMAIN` directly and `docker compose --env-file /mnt/mirr-volume/.env` loads environment variables without shell sourcing.
- **Passwords in `DATABASE_URL`:** percent-encode special characters (`@` is `%40`) or use letters and digits only. A stray `@` makes the host parse wrongly and the error message prints part of the URL into the (public) Actions log. Rotate the password if that happens.
- Use the `+psycopg` driver prefix for the app and Alembic, but a **plain `postgresql://` URL for `pg_dump`/`psql`**.
- Copy the exact pooler host from Supabase → Connect; the example host in `.env.example` may not match your project.

## Local development and tests

Uses a real local Postgres and Redis (no SQLite, no local storage fallbacks).

```bash
docker compose -f docker-compose.dev.yml up -d      # Postgres + Redis
cp .env.example .env                                # DATABASE_URL=...localhost:5432/mirr?sslmode=disable
alembic upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
celery -A workers.tasks worker --loglevel=info -c 1  # in a second terminal
```

```bash
ruff check .
alembic check          # models must match migrations
pytest                 # real Postgres, moto for R2, Celery eager
```

Tests live in `backend/app/test_main.py` and `workers/test_tasks.py`. See `.github/workflows/ci.yml` for the exact environment CI uses.

## CI/CD and operations

| Workflow | Trigger | What it does |
| :--- | :--- | :--- |
| `ci.yml` | pull requests, reusable | Ruff, `alembic upgrade head`, `alembic check`, pytest (Postgres and Redis services), plus a no-push build of both Dockerfiles |
| `deploy-backend.yml` | push to `main` touching `backend/`, `workers/`, `db/`, `alembic/`, `services/`, `shared/`, `deploy/` or `requirements*.txt`; manual with an optional `tag` (rollback) | CI → build and push images to GHCR (`mir-api`, `mir-worker`, tagged with the commit SHA) → **deploy** (environment `production`, owner approval required) → export `openapi.json` and open a PR in `mirr-web` when `FRONTEND_REPO_PAT` is set |
| `ops.yml` | manual | `status`, `logs`, `restart-worker`, `rollback` over SSH |
| `keepalive.yml` | every 3 days | Calls `HEALTH_URL` so the free Supabase project never pauses |
| `provision-droplet.yml` | manual | Creates the Droplet through the DigitalOcean API |

Deploy mechanics: `deploy/release.sh` pulls the new images, runs `alembic upgrade head` in the API container, restarts services, polls `/health` for about 100 seconds and restores the previous containers on failure. **Migrations are not rolled back**, so they must be additive. Changes to `README.md`, `AGENTS.md` and `docs/` do not trigger a deploy. The GHCR packages must be public for the Droplet to pull them.

Full phone-first runbook, first-boot checklist and secrets list: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Frontend (`mirr-web`)

Public repo, TanStack Start + Vite + bun, deployed to Cloudflare Workers by Cloudflare Workers Builds on every push to `main` (other branches get preview URLs). It is also edited with Lovable (two-way GitHub sync) and coding agents, so it must stay Lovable-compatible. The API contract flows from this repo: `/openapi.json` is exported and synced to `mirr-web` (`src/api/openapi.json`), where TypeScript types are generated. Keep API changes additive and documented.

## Known limitations and planned work

- **Memory:** `deploy/docker-compose.yml` sets the worker's memory limit to 8 GB, but the Droplet was provisioned small (2 GB by default). Stem separation of a real song can be OOM-killed until the Droplet is resized.
- **Ownership checks fail open for old rows.** `get_session`, `analyze` and `separate` only reject a caller when the session's `user_id` is set and different. A session whose `user_id` is `NULL` (created before auth existed) is readable by any signed-in user. Planned fix: fail closed and backfill or delete legacy rows.
- **Client-supplied object key.** `POST /api/v1/analyze` falls back to a client-supplied `artifact_url` when the session has none, and the worker uses that URL's path as an R2 object key in the configured bucket. Normal sessions always store their own `artifact_url`, but object keys should only ever come from server-side records. Planned fix: remove the fallback.
- **Planned:** RLS on `alembic_version`; OpenAPI polish (stable `operationId`s, explicit error models, status enum); removing the legacy `/api/*` aliases.
- **Backups are not automated** (free Supabase has none). Manual command in the runbook; add automation once real user data exists.
- **Legacy code:** `frontend/` (an old Next.js app) is unused; the real frontend is `mirr-web`.
- Free-tier limits that can break the workflow: [`docs/FREE_TIER_LIMITS.md`](docs/FREE_TIER_LIMITS.md).

## Documentation map

- `AGENTS.md` — rules for coding agents and contributors (start here).
- `docs/RUNBOOK.md`, `docs/FREE_TIER_LIMITS.md`, `docs/R2_CORS.md` — operations, limits, R2 CORS.
- `docs/agents/` — agent workflow notes (issue tracker, triage labels, domain).
- `techstack.md`, `environments.md`, `Music-Analysis-Platform.md`, `implementation-alignment-report.md`, `BMAD_ORIENTATION.md` — planning and historical documents that may lag behind the code. When they disagree with this README, `AGENTS.md` or the runbook, those win.
