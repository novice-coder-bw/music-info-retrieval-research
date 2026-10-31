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
     - `region`: `fra1` (closest to Supabase Paris `eu-west-3`).
     - `size`: `s-5-4vcpu-12gb-80gb` (preflight will check availability against `/v2/sizes` and report alternatives if unavailable).
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
3. Configure `/opt/mir/.env` on the Droplet (as user `deploy` or `root`):
   ```bash
   install -d -o deploy -g deploy /opt/mir
   # Create /opt/mir/.env with required production environment variables (see Section 6)
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

## 6. GitHub Secrets & Droplet Environment Variables

### GitHub Actions Secrets
- `DIGITALOCEAN_TOKEN`: DigitalOcean API token with Droplets and SSH Keys permissions.
- `DROPLET_HOST`: Public IPv4 or domain name of `mirr-server`.
- `DROPLET_SSH_KEY`: Private SSH key for the `deploy` user.
- `DATABASE_URL`: Supabase session pooler connection string (port 5432).
- `BACKUP_PASSPHRASE`: Symmetric encryption passphrase for pg_dump backups.
- `R2_ENDPOINT`: Cloudflare R2 endpoint URL.
- `R2_BUCKET`: R2 bucket name (`music-info-retrieval-research-1`).
- `R2_ACCESS_KEY_ID`: Cloudflare R2 access key.
- `R2_SECRET_ACCESS_KEY`: Cloudflare R2 secret key.
- `FRONTEND_REPO_PAT`: GitHub Personal Access Token with repo access to `novice-coder-bw/mirr-web`.
- `TELEGRAM_BOT_TOKEN`: (Optional) Telegram bot token for failure alerts.
- `TELEGRAM_CHAT_ID`: (Optional) Telegram chat ID for failure alerts.
- `HEALTH_URL`: (Optional) Full URL to `https://$DOMAIN/health` for keepalive cron.

### Droplet `/opt/mir/.env`
```env
DOMAIN=api.yourdomain.com
TAG=latest
DATABASE_URL=postgresql+psycopg2://postgres.mghlumhhbjfeqvnmqrjs:<PASSWORD>@aws-0-eu-west-3.pooler.supabase.com:5432/postgres
REDIS_URL=redis://redis:6379/0
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_BUCKET=music-info-retrieval-research-1
R2_ACCESS_KEY_ID=<R2_KEY>
R2_SECRET_ACCESS_KEY=<R2_SECRET>
R2_PUBLIC_BASE_URL=https://<PUB_BUCKET>.r2.dev
SUPABASE_JWKS_URL=https://mghlumhhbjfeqvnmqrjs.supabase.co/auth/v1/.well-known/jwks.json
CORS_ORIGIN_REGEX=^https:\/\/(.*\.)?(lovable\.app|lovableproject\.com|pages\.dev)$
MAX_UPLOAD_MB=100
ALLOW_PLACEHOLDER_STEMS=0
```
