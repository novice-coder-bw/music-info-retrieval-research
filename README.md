# Music Analysis Platform (mirr)

A FastAPI + Celery backend for music information retrieval: upload a track, analyze it (BPM, key, structure) and separate it into four stems (`drums`, `bass`, `other`, `vocals`) with Demucs.

| What | Where |
| :--- | :--- |
| API (production) | `https://mirr-web.duckdns.org` — `GET /health` is public; interactive docs at `/docs`; contract at `/openapi.json` |
| Frontend "Stemlab" | `https://mirr-web.novice-coder.workers.dev` — repo [`novice-coder-bw/mirr-web`](https://github.com/novice-coder-bw/mirr-web) |
| Database / Auth | Supabase project `mirr-web` (ref `mghlumhhbjfeqvnmqrjs`, eu-west-3, Postgres 17) |
| Object storage | Cloudflare R2 bucket `music-info-retrieval-research-1` |
| Compute | DigitalOcean Droplet `mirr-server` (Docker Compose: Caddy, API, Celery worker, Redis) |
| Config on Droplet | `/opt/mir/.env` (no block storage volume) |

This repository is **public**. Never commit secrets, and remember GitHub Actions logs are public too.

## Architecture

```
Browser (mirr-web, Cloudflare Workers)
   │ Supabase Auth → JWT              │ presigned PUT / GET (direct to R2)
   ▼                                  ▼
 Caddy ─▶ FastAPI (api) ─ Celery ─ Redis        Cloudflare R2
              │              │
              └── Supabase Postgres (session pooler) ◀┘
 (Caddy, api, worker, redis on one Droplet via Docker Compose)
```

### Request flow: upload → analyze → separate

1. Frontend signs in with Supabase Auth; every API call sends `Authorization: Bearer <access token>`.
2. `POST /api/v1/uploads/presign` validates type/size, records an upload intent, returns a presigned R2 PUT URL.
3. Browser uploads straight to R2 (bucket CORS must allow the frontend origin; see `docs/R2_CORS.md`).
4. `POST /api/v1/uploads/complete` verifies the object in R2, creates the session, enqueues analysis.
5. Celery runs analysis; stages update in Postgres.
6. `POST /api/v1/separate` enqueues Demucs; stems land in R2 and on the session.
7. Frontend polls `GET /api/v1/session/{file_id}`.

## API

All routes except `GET /health` require a valid Supabase JWT. Users only access their own sessions. `/docs`, `/redoc`, `/openapi.json` are public.

| Route | Purpose |
| :--- | :--- |
| `GET /health` | Public dependency checks |
| `POST /api/v1/uploads/presign` | Presigned R2 PUT |
| `POST /api/v1/uploads/complete` | Finalize upload, create session, enqueue analysis |
| `POST /api/v1/upload` | Multipart upload through the API |
| `GET /api/v1/session/{file_id}` | Session + stages + stems |
| `POST /api/v1/analyze` | Enqueue analysis |
| `POST /api/v1/separate` | Enqueue 4-stem separation |

Deprecated unversioned aliases under `/api/*` still exist; new code must use `/api/v1`.

**Stage status vocabulary:** `pending | active | completed | failed`.

## Configuration

Production settings live in **`/opt/mir/.env`** on the Droplet (never in git). Deploys do not overwrite that file unless `PROD_ENV_FILE` is set and sync runs. See `.env.example` and `docs/RUNBOOK.md`.

| Variable | Notes |
| :--- | :--- |
| `DATABASE_URL` | Required. Supabase session pooler, `postgresql+psycopg://...` |
| `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | Required |
| `REDIS_URL` | Compose default `redis://redis:6379/0` |
| `DOMAIN` | Required for Caddy TLS and health checks |
| `CORS_ORIGIN_REGEX` | Allowed frontend origins |
| `MAX_UPLOAD_MB` | Default `100` |
| `ALLOW_PLACEHOLDER_STEMS` | `0` in production |

## Local development and tests

```bash
docker compose -f docker-compose.dev.yml up -d
cp .env.example .env
alembic upgrade head
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
celery -A workers.tasks worker --loglevel=info -c 1
```

```bash
ruff check .
alembic check
pytest
```

## CI/CD

| Workflow | Role |
| :--- | :--- |
| `ci.yml` | Ruff, Alembic, pytest, Dockerfile builds |
| `deploy-backend.yml` | Build/push GHCR images → deploy to Droplet → optional OpenAPI sync to `mirr-web` |
| `ops.yml` | status / logs / restart-worker / rollback |
| `keepalive.yml` | Hit `/health` so free Supabase stays awake |
| `provision-droplet.yml` | Create Droplet only (no block volume) |

Full runbook: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Frontend (`mirr-web`)

TanStack + Vite on Cloudflare Workers; also edited with Lovable. API contract is synced from this repo's `/openapi.json`. Keep API changes additive.

## Known limitations

- Worker memory limit in compose is 8 GB; a small Droplet can OOM on real Demucs runs until resized.
- Ownership checks still fail-open for legacy rows with `user_id` NULL (see earlier notes); new code must fail closed.
- Backups are manual on free Supabase.
- Legacy `frontend/` tree is unused.

## Documentation map

- `AGENTS.md` — agent/contributor rules.
- `docs/RUNBOOK.md`, `docs/FREE_TIER_LIMITS.md`, `docs/R2_CORS.md` — ops.
- Historical docs may lag; when they conflict with this README or the runbook, those win.
