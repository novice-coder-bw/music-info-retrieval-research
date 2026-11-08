# mirr-server Operations Runbook

This runbook covers day-to-day operations for `mirr-server` hosted on DigitalOcean, Supabase Postgres, and Cloudflare R2.
The project is maintained and operated entirely from mobile devices via GitHub and the DigitalOcean mobile app.

---

## 1. Droplet Provisioning (Initial Setup)

To provision the `mirr-server` droplet on DigitalOcean using GitHub Actions:

1. **DigitalOcean Custom Token**:
   - In DigitalOcean, create a custom personal access token scoped to Droplets (read/write) and SSH Keys (read).
   - In GitHub repository settings, under **Environments**, create/configure environment `production`.
   - Add the secret `DIGITALOCEAN_TOKEN` containing your token.

2. **Register SSH Public Keys in DigitalOcean**:
   - Under DigitalOcean Settings -> Security -> SSH Keys, add:
     - Phone SSH public key (e.g., named `phone-termius`).
     - GitHub Actions deploy key public key (e.g., named `gh-actions-deploy`).

3. **Run the Provisioning Workflow**:
   - On GitHub (Actions tab or via mobile browser), select `provision-droplet` -> **Run workflow**.
   - Inputs:
     - `ssh_key_names`: Comma-separated names of the registered SSH keys (e.g. `phone-termius,gh-actions-deploy`).
     - `region`: `mkc1` (default, to avoid DigitalOcean capacity restrictions in `fra1`; Supabase is in Paris `eu-west-3`).
     - `size`: `s5-2vcpu-2gb-30gb` (preflight will check availability against `/v2/sizes` and report alternatives if unavailable).
   - When prompted, approve the deployment in environment `production` via GitHub mobile app.
   - The workflow creates the droplet and verifies public IPv4 and IPv6 assignment. Note that IP addresses are not printed in GitHub logs to preserve privacy on a public repository. Check IP addresses in the DigitalOcean mobile app.

4. **Droplet First-Boot & Bootstrap Completion**:
   - On boot, `cloud-init` installs Docker, UFW, packages, configures the `deploy` user, swap, and SSH hardening.
   - Wait for the bootstrap marker file:
     ```bash
     cat /var/lib/cloud/instance/mirr-bootstrap.done
     ```
   - Proceed with the First-Boot Checklist below.

---

## 2. First-Boot Checklist

1. Wait for `/var/lib/cloud/instance/mirr-bootstrap.done` to be created.
2. Verify DNS records:
   - Point your DNS `A` record (IPv4) and `AAAA` record (IPv6) to the Droplet's public IPs.
3. Configure `/mnt/mirr_volume/.env` on the Droplet (as user `deploy` or `root`):
   ```bash
   install -d -o deploy -g deploy /mnt/mirr_volume
   # Create /mnt/mirr_volume/.env with required production environment variables (see Section 6)
   chmod 600 /mnt/mirr_volume/.env
   ```
4. Initial deployment:
   - Run the GitHub Actions `deploy-backend.yml` workflow to build images, push to GHCR, copy configuration, run Alembic migrations, and start Docker Compose services.

---

## 3. Phone-First Operations

All operational tasks can be triggered and monitored from your phone:

- **Approve Deploys**:
  - The `deploy-backend.yml` workflow pauses at the `production` environment step.
  - Approve the deployment notification directly inside the GitHub mobile app.

- **Routine Operations & Diagnostics (`ops.yml`)**:
  - In GitHub Actions -> `ops` -> **Run workflow**:
    - `action`:
      - `status`: Check `docker compose ps` and memory/swap usage.
      - `logs`: Fetch the last N lines of container logs (default: 200).
      - `restart-worker`: Restart the Celery worker container.
      - `rollback`: Roll back to a previous image tag without database rollback.
    - `tag`: Specify container image tag when rolling back.
  - Results and command outputs are printed to the GitHub Actions Job Summary. Secrets and `.env` are never printed.

- **Checking Health Status**:
  - `GET https://$DOMAIN/health`
  - Returns JSON booleans:
    - `status`: `ok` or `degraded`
    - `database`: `true` (SELECT 1 on Supabase Postgres)
    - `redis`: `true` (PING)
    - `storage`: `true` (R2 head_bucket)
    - `worker`: `true` (Celery ping)
  - HTTP 503 is returned if any component is unreachable.

---

## 4. Rollback Procedure

Migrations are strictly additive, so code rollbacks do not roll back Alembic migrations.

1. **Option A: Via `ops.yml`**:
   - Go to Actions -> `ops` -> **Run workflow**.
   - Select `action: rollback` and provide the previous `tag` (e.g. Git commit SHA or `.tag` from `/opt/mir/.tag`).
2. **Option B: Via `deploy-backend.yml`**:
   - Run `deploy-backend.yml` manually with the `tag` input set to the previous good tag. This skips the build step and deploys the specified tag directly.

---

## 5. Neon to Supabase Migration Procedure

To migrate historical data from Neon Postgres to Supabase:
1. Ensure both `NEON_URL` and `SUPABASE_URL` are accessible.
2. Run the provided helper script:
   ```bash
   ./scripts/migrate_neon_to_supabase.sh
   ```
3. The script requires interactive confirmation (`set -euo pipefail`), runs `pg_dump --data-only --no-owner --no-privileges` from `NEON_URL`, and pipes directly to `psql SUPABASE_URL`.

---

## 6. Backups (not automated)

Free-tier Supabase does not provide automatic daily backups. Automated database backups are intentionally disabled for now because the public schema starts empty and data is regenerable. Re-add automation once real user data exists.

To perform a manual one-off backup on the Droplet before risky operations or migrations, run:

```bash
# Read DATABASE_URL safely from persistent volume and dump using plain postgresql:// URL (stripping +psycopg driver prefix)
DATABASE_URL=$(grep -E '^[[:space:]]*DATABASE_URL[[:space:]]*=' /mnt/mirr_volume/.env | tail -n 1 | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '\r' | tr -d ' ')
DUMP_URL=$(echo "$DATABASE_URL" | sed 's/+psycopg//')
pg_dump "$DUMP_URL" --clean --if-exists --no-owner --no-privileges | gzip > "/opt/mir/manual_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

---

## 7. GitHub Secrets & Droplet Environment Variables

### Required GitHub Secrets
- `DIGITALOCEAN_TOKEN`: DigitalOcean API token with Droplets and SSH Keys permissions (stored in `production` environment).
- `DROPLET_HOST`: Public IPv4 or domain name of `mirr-server`.
- `DROPLET_SSH_KEY`: Private SSH key for the `deploy` user.

### Optional GitHub Secrets
- `PROD_ENV_FILE`: Raw text or Base64-encoded content of `/mnt/mirr_volume/.env`. When present, GitHub Actions automatically sanitizes mobile formatting errors (smart quotes, CRLF, unicode dashes) and delivers it atomically via Base64 decoding over SSH.
- `HEALTH_URL`: Full URL to `https://$DOMAIN/health` for keepalive cron.
- `FRONTEND_REPO_PAT`: Fine-grained GitHub Personal Access Token limited specifically to repository `novice-coder-bw/mirr-web` (used to sync `openapi.json`).
- `TELEGRAM_BOT_TOKEN`: Telegram bot token for deployment failure alerts.
- `TELEGRAM_CHAT_ID`: Telegram chat ID for deployment failure alerts.

*(Note: `DATABASE_URL` and `R2_*` credentials are read from `/mnt/mirr_volume/.env` on the Droplet and can be managed directly on the volume or injected via `PROD_ENV_FILE`).*

### Privacy and Object Storage URLs
By default, the R2 bucket should remain private. When `R2_PUBLIC_BASE_URL` is omitted, the backend generates short-lived presigned GET URLs (1-hour expiry) for artifact streaming and stem playback, ensuring private user audio cannot be accessed publicly without authorization. Setting `R2_PUBLIC_BASE_URL` exposes artifacts to anyone with the object key.

### Droplet `/mnt/mirr_volume/.env`
```env
DOMAIN=api.yourdomain.com
TAG=latest
DATABASE_URL=postgresql+psycopg://postgres.mghlumhhbjfeqvnmqrjs:<PASSWORD>@aws-0-eu-west-3.pooler.supabase.com:5432/postgres
REDIS_URL=redis://redis:6379/0
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_BUCKET=music-info-retrieval-research-1
R2_ACCESS_KEY_ID=<R2_KEY>
R2_SECRET_ACCESS_KEY=<R2_SECRET>
# Optional: Set R2_PUBLIC_BASE_URL only if public unauthenticated access to audio files is explicitly desired
# R2_PUBLIC_BASE_URL=https://<PUB_BUCKET>.r2.dev
SUPABASE_JWKS_URL=https://mghlumhhbjfeqvnmqrjs.supabase.co/auth/v1/.well-known/jwks.json
CORS_ORIGIN_REGEX=^https:\/\/(.*\.)?(lovable\.app|lovableproject\.com|pages\.dev)$
MAX_UPLOAD_MB=100
ALLOW_PLACEHOLDER_STEMS=0
```
