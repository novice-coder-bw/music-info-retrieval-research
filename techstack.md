# Tech Stack

This document outlines the core technology stack used in the Music Analysis Platform.

## Core Architecture

| Component | Technology |
| :--- | :--- |
| **Language** | Python 3.12 |
| **API Framework** | FastAPI (2026 stable) |
| **Task Queue** | Celery (2026 stable) |
| **Message Broker / Result Backend** | Redis (2026 stable) |
| **Containerization** | Docker |
| **Database** | Neon Postgres (Managed Serverless) |
| **Migrations** | Alembic |
| **Object Storage** | Cloudflare R2 |

## Frontend

| Component | Technology |
| :--- | :--- |
| **Framework** | Next.js (2026 stable) |
| **Library** | React (2026 stable) |
| **UI Components** | shadcn/ui |
| **Styling** | Tailwind CSS |
| **Audio Visualization** | WaveSurfer.js (2026 stable) |

## Audio Processing & Music Information Retrieval (MIR)

| Library | Purpose |
| :--- | :--- |
| **Demucs** | HTDemucs v4 (Source separation) |
| **Basic-Pitch** | Note detection / Audio-to-MIDI |
| **madmom** | Audio signal processing / Beat tracking |
| **essentia** | Music analysis / Feature extraction |
| **pyableton** | Ableton Live integration |

## Infrastructure & Environment

### Redis with Docker
To run Redis locally for development using Docker:

1. **Start Redis Container:**
   ```bash
   docker run --name music-redis -p 6379:6379 -d redis:latest
   ```

2. **Verify it's running:**
   ```bash
   docker ps
   ```

3. **Connection Config:**
   Ensure your `.env` or configuration files point the Celery broker/backend to:
   `redis://localhost:6379/0`
