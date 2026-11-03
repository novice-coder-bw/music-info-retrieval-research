<!-- bmad:context -->
<!-- Verified 2026-08-14 against 7eb0e67. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## Music Analysis Platform

MIR platform for stem separation. FastAPI/Node, SQLAlchemy, Celery/Redis. Planning in `.scratch/`, triage labels in `docs/agents/triage-labels.md`.

## Policy

- Lightning AI Studio: No virtualenvs. Use the single default `python3` environment.
- Tests must be hermetic: force local storage backends and in-process workers.
- If Redis/Celery broker is unreachable, fall back to in-process analysis.
- Do not attempt to create virtualenvs; Studio environment manages dependencies.

## Where things are

- Issues/Specs: `.scratch/<feature-slug>/`
- Domain context: `CONTEXT.md` and `docs/adr/`
- Triage vocabulary: `docs/agents/triage-labels.md`

## Running and verifying

- `startup.sh`: installs dependencies and starts Redis (idempotent).
- `run_all.sh`: runs all services (backend/Celery/frontend).
- Backend tests: `python3 -m pytest backend/app/test_main.py -q`

## Known pitfalls

- Celery broker issues: do not add long retry loops; the app handles graceful degradation to in-process execution automatically.
- Database/Persistence: if `DATABASE_URL` is unset, it defaults to SQLite and local uploads. Never assume durability without configuration.

<!-- /bmad:context -->
