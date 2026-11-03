# Environments & Infrastructure

This document outlines the deployment environments and infrastructure topology for the Music Analysis Platform.

## Architecture Overview

```
                      +-----------------------------+
                      |   Lovable Web Frontend      |
                      | (novice-coder-bw/mirr-web)  |
                      +--------------+--------------+
                                     |
                                     | HTTPS / WSS
                                     v
                       +-------------+-------------+
                       |   DigitalOcean Droplet    |
                       |       (mirr-server)       |
                       |  Ubuntu 24.04 (4vCPU/12GB)|
                       +-------------+-------------+
                                     |
                 +-------------------+-------------------+
                 |                                       |
                 v                                       v
   +-----------------------------+       +-----------------------------+
   |      Supabase Postgres      |       |        Cloudflare R2        |
   |      PostgreSQL 17          |       |     Object Storage S3-API   |
   |      (eu-west-3, Paris)     |       | (music-info-retrieval-res..) |
   +-----------------------------+       +-----------------------------+
```

## Production Environment

- **Droplet Host**:
  - Name: `mirr-server`
  - OS: Ubuntu 24.04 LTS
  - Specs: 4 vCPU, 12 GB RAM, 80 GB SSD
  - Region: `fra1` (Frankfurt, lowest latency to Supabase Paris `eu-west-3`)
  - Firewall (UFW): Ports 22 (SSH), 80 (HTTP), 443 (HTTPS) only.
  - Services: Caddy (reverse proxy + auto TLS), FastAPI API (Uvicorn), Celery Worker (Demucs/PyTorch), Redis (internal broker).

- **Database (Supabase)**:
  - Managed PostgreSQL 17 in `eu-west-3` (Paris).
  - Connected via Supabase Session Pooler (port 5432).
  - Uses Row Level Security (RLS) on public tables.

- **Object Storage (Cloudflare R2)**:
  - Bucket: `music-info-retrieval-research-1`.
  - Accessible directly via client presigned PUT URLs for uploads, and public base URL / presigned URLs for stems and raw audio playback.

- **Frontend (Lovable)**:
  - Hosted in repository `novice-coder-bw/mirr-web`.
  - Directly subscribes to Supabase Realtime for task progress updates.

## Development Environment

- Run Postgres and Redis using `docker-compose.dev.yml`.
- Standard Python 3.12 environment with direct dependencies.
- No SQLite or in-process local fallbacks.
