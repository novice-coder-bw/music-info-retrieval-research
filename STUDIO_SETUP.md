# Lightning AI Studio Environment Persistence Guide

This document outlines how to maintain environment state and automate your startup process in Lightning AI Studio.

## Why is my environment resetting?

Lightning AI Studios use a persistent file system for your home directory (`/home/studio/`), but the **OS-level environment** is volatile. When a Studio shuts down, the container runtime is destroyed. This means:
- System-level packages are wiped.
- Background services (like Redis) stop.
- Running processes are killed.

To maintain state, you must ensure that all dependencies and data are stored within your project's persistent directory structure.

## Strategies for Persistence

### 1. Project-Local Environments
- **Python:** This Studio does **not** allow creating virtualenvs — it has a single default conda environment (`cloudspace`). Dependencies are installed there with `pip install -r backend/requirements.txt`. (If you run these scripts on a non-Studio host where `backend/venv` exists, that venv is used instead.)
- **Node.js:** `node_modules` will persist as long as they are installed in your `frontend/` directory.

### 2. Redis Data Persistence
While the Redis *service* must be restarted, you can make the *data* persistent by mounting a local directory as a volume. Use this command to start Redis:

```bash
docker run --name music-redis -p 6379:6379 -d \
  -v $(pwd)/redis-data:/data \
  redis:latest redis-server --appendonly yes
```

## Automating Startup (`startup.sh`)

The repo ships a ready-made `startup.sh` in the root directory (no need to write it yourself). Run it manually, or wire it into Studio startup settings (below), so it runs after every boot to re-initialize your environment.

It performs these steps (all idempotent — safe to re-run):

1. **Backend deps** — installs `backend/requirements.txt` into the active Python (the Studio's default conda env; Studio forbids creating venvs). Uses `backend/venv` if it already exists on a non-Studio host.
2. **Frontend deps** — runs `npm install` in `frontend/` only if `node_modules` is missing.
3. **Redis** — starts the existing `music-redis` container, or creates it with a persistent `./redis-data` volume mounted.
4. **Migrations** — runs `alembic upgrade head` only if `DATABASE_URL` is set in `.env`.

```bash
chmod +x startup.sh   # ensure it is executable
./startup.sh          # run from the repo root
```

### Wiring `startup.sh` into Studio startup settings

To run it automatically on every Studio boot:

1. Make sure it is executable: `chmod +x startup.sh`.
2. In the Lightning AI Studio UI, open **Studio → Settings → Startup** (or the equivalent "startup command"/"on start" hook for your Studio version).
3. Set the startup command to run the script from your project directory, e.g.:
   ```bash
   cd /teamspace/studios/this_studio/music-info-retrieval-research && ./startup.sh
   ```
   (Use the actual absolute path to your repo.)
4. Save and restart the Studio to confirm the script runs automatically and prints the completion banner.

> If your Studio doesn't expose a startup hook, run `./startup.sh` manually after each boot — it's designed to be a single command that restores the full environment.

## Running the Stack (`run_all.sh`)

The repo also ships a ready-made `run_all.sh` that launches the whole stack concurrently and stops everything on Ctrl-C:

```bash
./run_all.sh
```

It starts:
- **Backend** — FastAPI via `uvicorn app.main:app` on `http://localhost:8000`
- **Celery worker** — `celery -A workers.tasks worker` (only if Celery is installed in the venv)
- **Frontend** — Next.js dev server on `http://localhost:3000`

*Note: Ensure both files are executable: `chmod +x startup.sh run_all.sh`.*
