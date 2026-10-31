# Tech Stack

This document details the core technologies used in the Music Analysis Platform.

## Core Architecture

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.12 | Backend and worker runtime |
| **API Framework** | FastAPI | Async REST API under `/api/v1` |
| **Task Queue** | Celery 5.x | Background processing with concurrency 1 |
| **Message Broker** | Redis 7 | Internal Redis broker (appendonly, non-eviction) |
| **Database** | Supabase Postgres 17 | Hosted in `eu-west-3` (Paris) |
| **Database Pooler** | Supabase Session Pooler | Port 5432 with `sslmode=require` |
| **ORM & Migrations** | SQLAlchemy 2.0 + Alembic | Strictly additive schema migrations |
| **Object Storage** | Cloudflare R2 | S3-compatible storage via boto3 |
| **Web Server / TLS** | Caddy | Automatic HTTPS and reverse proxying |
| **Host Environment** | DigitalOcean Droplet | Ubuntu 24.04 (Docker Compose) |

## Audio Processing & Music Information Retrieval (MIR)

| Library | Purpose |
| :--- | :--- |
| **Demucs (HTDemucs v4)** | Source separation (drums, bass, other, vocals) |
| **PyTorch (CPU)** | Deep learning model inference for Demucs |
| **Essentia / Librosa / NumPy** | Feature extraction (BPM, key, structure) |

## Frontend

| Component | Repository |
| :--- | :--- |
| **Web Client** | `novice-coder-bw/mirr-web` (Lovable project "Stem Studio") |
| **Client Realtime** | Supabase Realtime subscriptions to `sessions` table |
