# Music Analysis Platform Scaffold

This repository contains a minimal scaffold for the Music Analysis Platform MVP.

## Frontend
- `frontend/`: Next.js application shell
- `frontend/components/UploadPanel.tsx`: initial drag-and-drop upload UI

## Backend
- `backend/`: FastAPI app scaffold
- `backend/app/main.py`: upload endpoint placeholder
- `backend/requirements.txt`: backend dependencies

## Workers
- `workers/tasks.py`: Celery task scaffold for audio analysis

## Shared
- `shared/schemas.py`: common Pydantic models and schemas

## Next Steps
1. Install frontend dependencies:
   - `cd frontend && npm install`
2. Install backend dependencies:
   - `cd backend && python3 -m pip install -r requirements.txt`
3. Run frontend:
   - `cd frontend && npm run dev`
4. Run backend:
   - `cd backend`
   - `python -m venv venv`
   - `venv\Scripts\activate` (or `source venv/Scripts/activate` on Linux/macOS)
   - `pip install -r requirements.txt`
   - `uvicorn app.main:app --reload`
   *(If not activated, use `./venv/Scripts/python -m uvicorn app.main:app --reload`)*
