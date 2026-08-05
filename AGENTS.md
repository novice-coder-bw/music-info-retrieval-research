# Agent instructions

## Agent skills

### Issue tracker

This repo tracks work as local markdown files under .scratch/. See docs/agents/issue-tracker.md.

### Repo-specific conventions

- Use the backend virtual environment at `backend/venv` for Python test execution.
- Run backend tests from the repo root or `backend/` with:
  - `backend/venv/Scripts/python -m pytest -q`
- Do not rely on a global `pytest` installation for this repository.
- Story progress is tracked in `_bmad-output/implementation-artifacts/*.md` and `sprint-status.yaml`; update those files when implementation is complete.

### Triage labels

This repo uses the default triage vocabulary with the canonical roles needs-triage, needs-info, ready-for-agent, ready-for-human, and wontfix. See docs/agents/triage-labels.md.

### Domain docs

This repo uses a single-context layout with a root CONTEXT.md and docs/adr/. See docs/agents/domain.md.
