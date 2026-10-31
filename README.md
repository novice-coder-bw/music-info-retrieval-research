# Music Analysis Platform

A FastAPI + Celery backend platform for music information retrieval: upload audio, analyze features (BPM, key, structure), and separate audio into stems (drums, bass, other, vocals) using Demucs.

The platform runs on a DigitalOcean Droplet via Docker Compose, backed by **Supabase Postgres (PostgreSQL 17)** and **Cloudflare R2** for durable object storage. The frontend is built in Lovable and hosted in the separate repository [`novice-coder-bw/mirr-web`](https://github.com/novice-coder-bw/mirr-web).

## Repository layout

| Path | Purpose |
| :--- | :--- |
| `backend/` | FastAPI application (`backend/app/main.py`) — health, presigned upload, analysis, separation, sessions |
| `backend/requirements.txt` | Core API dependencies (FastAPI, uvicorn, SQLAlchemy, psycopg, boto3, PyJWT) |
| `requirements-worker.txt` | Celery worker dependencies (Demucs, CPU PyTorch, librosa/essentia, etc.) |
| `workers/` | Celery worker tasks (`workers/tasks.py`) — `analyze_audio_task`, `separate_stems_task` |
| `services/storage.py` | S3-compatible Cloudflare R2 object storage client (no local fallbacks) |
| `db/` | SQLAlchemy engine/models/store for Supabase Postgres |
| `alembic/` | Database migrations for the public schema |
| `deploy/` | Docker Compose, Caddyfile, Dockerfiles, cloud-init, and release script for Droplet deployment |
| `.github/workflows/` | CI/CD workflows (testing, image builds, zero-downtime release, ops, and db backup) |
| `docs/` | Operations runbook (`docs/RUNBOOK.md`) and free-tier limits (`docs/FREE_TIER_LIMITS.md`) |

## API Endpoints

All primary routes are mounted under `/api/v1` (with `/api/*` supported as backwards-compatible aliases):

- `GET /health` — Service health check (Postgres, Redis, R2, Celery ping)
- `POST /api/v1/uploads/presign` — Get presigned R2 PUT URL for direct client uploads (WAV/MP3)
- `POST /api/v1/uploads/complete` — Finalize upload, create session, enqueue analysis
- `POST /api/v1/upload` — Multipart direct upload fallback (deprecated alias)
- `GET /api/v1/session/{file_id}` — Fetch session details, status, and stems
- `POST /api/v1/analyze` — Request MIR feature analysis
- `POST /api/v1/separate` — Request 4-stem Demucs separation (`drums`, `bass`, `other`, `vocals`)

## Local Development

Local development uses a local PostgreSQL instance and Redis instance (e.g. via `docker-compose.dev.yml`).

```bash
# 1. Start local Postgres and Redis
docker compose -f docker-compose.dev.yml up -d

# 2. Configure .env from .env.example
cp .env.example .env
# Edit DATABASE_URL to point to postgresql+psycopg2://postgres:postgres@localhost:5432/postgres

# 3. Apply database migrations
alembic upgrade head

# 4. Run the API server
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# 5. Run Celery worker
celery -A workers.tasks worker --loglevel=info -c 1
```

## Running Tests

Tests run against a real Postgres database (`DATABASE_URL`), mock Cloudflare R2 using `moto`, and execute Celery eagerly:

```bash
pytest
ruff check .
```
