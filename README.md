# Music Analysis Platform

A FastAPI + Next.js platform for music information retrieval: upload audio, analyze it, and separate it into stems. The MVP ships a working API contract, Celery/Redis worker queue, and durable persistence (Neon Postgres + Cloudflare R2) with robust local fallbacks.

## Repository layout

| Path | Purpose |
| :--- | :--- |
| `backend/` | FastAPI app (`backend/app/main.py`) — upload, analyze, separate, session endpoints |
| `backend/requirements.txt` | Backend Python dependencies |
| `workers/` | Celery app + tasks (`workers/tasks.py`): `analyze_audio`, `separate_stems` (Demucs with placeholder fallback) |
| `services/storage.py` | Object-storage adapter — Cloudflare R2 (S3-compatible) with a local `uploads/` fallback |
| `db/` | SQLAlchemy engine/models/store + SQLite fallback when Postgres is not configured |
| `shared/schemas.py` | Common Pydantic models shared by API and worker layers |
| `alembic/` | Database migrations |
| `frontend/` | Next.js app — upload UI, analyze + separate + session proxy routes |

## API endpoints (backend)

- `POST /api/upload` — upload an audio file (WAV/MP3)
- `GET /api/session/{file_id}` — fetch a session's status/stages
- `POST /api/analyze` — run analysis on an uploaded file
- `POST /api/separate` — separate a file into stems (`drums`, `bass`, `other`, `vocals`)

## Develop / run locally

The repo ships two executable scripts. Run them from the repo root.

```bash
chmod +x startup.sh run_all.sh   # already executable, shown for safety

./startup.sh   # install deps + start Redis (idempotent)
./run_all.sh   # run backend, Celery worker, and frontend together
```

- `startup.sh` installs `backend/requirements.txt`, runs `npm install` in `frontend/`, starts the `music-redis` Docker container (data persisted in `./redis-data`), and applies Alembic migrations when `DATABASE_URL` is set.
- `run_all.sh` starts the FastAPI backend (`http://localhost:8000`), the Celery worker, and the Next.js dev server (`http://localhost:3000`). **Ctrl-C stops all of them.** The worker is started only if Celery is installed in the active Python.

### Manual commands

If you prefer to run the pieces yourself:

```bash
# Backend
python3 -m pip install -r backend/requirements.txt
cd backend && python3 -m uvicorn app.main:app --reload

# Celery worker (from repo root)
python3 -m celery -A workers.tasks worker --loglevel=info

# Frontend
cd frontend && npm install && npm run dev
```

### Environment & persistence

- **This project is developed in Lightning AI Studio**, which **does not allow creating virtualenvs** — it provides a single default conda environment. All backend dependencies are installed into that default Python (`python3`); there is no `backend/venv`. `startup.sh`/`run_all.sh` prefer `backend/venv` only if it already exists on a non-Studio host.
- Redis *data* persists across Studio restarts via the `./redis-data` Docker volume; the container itself is (re)started by `startup.sh`. See `STUDIO_SETUP.md`.
- Copy `.env.example` to `.env` and fill in `DATABASE_URL` (Neon Postgres) and R2 credentials to enable real persistence/object storage. When they are empty/unset, the app degrades to a local SQLite store and local `uploads/` (it never claims real durability it didn't use).
- Celery graceful degradation: analysis and separation run in-process when the Redis broker is unreachable or a worker is absent, switching to the async worker path whenever Redis + the worker are up.

## Frontend proxy

The Next.js proxy routes forward `/api/*` to the backend at `http://localhost:8000` by default. If your backend runs elsewhere, set `NEXT_PUBLIC_BACKEND_URL` before starting the frontend.

## Tests

Backend tests (run with the default Python, since no venv exists in Studio):

```bash
python3 -m pytest backend/app/test_main.py -q
```

The test suite is hermetic: it forces local storage backends and the in-process worker path, so it never depends on live Postgres, R2, Redis, or a running Celery worker.

