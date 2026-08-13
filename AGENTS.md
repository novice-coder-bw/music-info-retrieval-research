# Agent instructions

## Agent skills

### Issue tracker

This repo tracks work as local markdown files under .scratch/. See docs/agents/issue-tracker.md.

### Repo-specific conventions

- This repo is developed in Lightning AI Studio, which **does not allow creating virtualenvs** — there is a single default conda environment (`python3` on PATH). There is no `backend/venv`. Run backend tests with that default Python:
  - From the repo root or `backend/`: `python3 -m pytest -q`
- If a `backend/venv` happens to exist (e.g. on a non-Studio host), use `backend/venv/bin/python -m pytest -q`.
- Do not attempt `python -m venv` / virtualenv creation; Studio rejects it.
- The test suite (`backend/app/test_main.py`) is hermetic: its autouse fixture forces local storage backends and the in-process worker path, so tests never depend on live Postgres, R2, Redis, or a running Celery worker.
- The Celery app (`workers/tasks.py`) fails fast when the Redis broker is unreachable (`broker_reachable()`), letting the FastAPI app fall back to in-process analysis/separation. Do not add long broker-retry loops.
- Story progress is tracked in `_bmad-output/implementation-artifacts/*.md` and `sprint-status.yaml`; update those files when implementation is complete.

### Triage labels

This repo uses the default triage vocabulary with the canonical roles needs-triage, needs-info, ready-for-agent, ready-for-human, and wontfix. See docs/agents/triage-labels.md.

### Domain docs

This repo uses a single-context layout with a root CONTEXT.md and docs/adr/. See docs/agents/domain.md.
