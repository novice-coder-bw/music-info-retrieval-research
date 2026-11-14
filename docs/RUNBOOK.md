# mirr-server Operations Runbook

This runbook covers day-to-day operations for `mirr-server` hosted on DigitalOcean, Supabase Postgres, and Cloudflare R2.
The project is maintained and operated entirely from mobile devices via GitHub and the DigitalOcean mobile app.

**Config lives at `/opt/mir/.env` on the Droplet root disk.** There is no DigitalOcean block storage volume.

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
     - `region`: `mkc1` (default).
     - `size`: `s5-2vcpu-2gb-30gb` (preflight checks availability).
   - Approve the deployment in environment `production` via GitHub mobile app.
   - IP addresses are not printed in GitHub logs. Read them in the DigitalOcean app.

4. **Droplet First-Boot & Bootstrap Completion**:
   - On boot, `cloud-init` installs Docker, UFW, packages, configures the `deploy` user, swap, and SSH hardening.
   - Wait for the bootstrap marker:
     ```bash
     cat /var/lib/cloud/instance/mirr-bootstrap.done
     ```

5. **Update GitHub secret `DROPLET_HOST`** to the new Droplet public IP (or DNS name once DNS points at it).

---

## 2. First-Boot Checklist

1. Wait for `/var/lib/cloud/instance/mirr-bootstrap.done`.
2. Point DNS `A` / `AAAA` records at the Droplet public IPs.
3. Ensure GitHub secret `PROD_ENV_FILE` holds a full production `.env` (see Section 6), **or** create `/opt/mir/.env` on the Droplet as `deploy`:
   ```bash
   # as deploy — /opt/mir is already owned by deploy after cloud-init
   nano /opt/mir/.env   # paste vars, save
   chmod 600 /opt/mir/.env
   ```
4. Run **deploy-backend** (Actions). On first deploy, use **workflow_dispatch** with `sync_env: true` if relying on `PROD_ENV_FILE`.

---

## 3. Phone-First Operations

- **Approve Deploys**: `deploy-backend` pauses at the `production` environment; approve in the GitHub mobile app.
- **ops.yml**: `status`, `logs`, `restart-worker`, `rollback` (with optional `tag`).
- **Health**: `GET https://$DOMAIN/health` — JSON booleans for `status`, `database`, `redis`, `storage`, `worker`.

---

## 4. Rollback Procedure

Migrations are additive; code rollbacks do not roll back Alembic.

1. **ops.yml** → `action: rollback` + previous `tag`, or
2. **deploy-backend** manual run with `tag` set to the previous good SHA (skips build).

---

## 5. Neon to Supabase Migration

```bash
./scripts/migrate_neon_to_supabase.sh
```

Requires interactive confirmation. Do not run from agents without owner approval.

---

## 6. Backups (not automated)

Free-tier Supabase has no automatic daily backups. Manual dump on the Droplet:

```bash
DATABASE_URL=$(grep -E '^[[:space:]]*DATABASE_URL[[:space:]]*=' /opt/mir/.env | tail -n 1 | cut -d '=' -f2- | tr -d '"' | tr -d "'" | tr -d '\r' | tr -d ' ')
DUMP_URL=$(echo "$DATABASE_URL" | sed 's/+psycopg//')
pg_dump "$DUMP_URL" --clean --if-exists --no-owner --no-privileges | gzip > "/opt/mir/manual_backup_$(date +%Y%m%d_%H%M%S).sql.gz"
```

---

## 7. GitHub Secrets & Droplet Environment

### Required GitHub Secrets
- `DIGITALOCEAN_TOKEN` — Droplets + SSH Keys (production environment).
- `DROPLET_HOST` — public IPv4 or hostname of `mirr-server`.
- `DROPLET_SSH_KEY` — private key for the `deploy` user.

### Optional GitHub Secrets
- `PROD_ENV_FILE` — raw or Base64 content of production `.env`. When present (and on push, or manual with `sync_env: true`), Actions sanitizes and writes `/opt/mir/.env`.
- `HEALTH_URL` — for keepalive cron.
- `FRONTEND_REPO_PAT` — sync `openapi.json` to `mirr-web`.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — deploy failure alerts.

`DATABASE_URL`, `R2_*`, etc. live only in `/opt/mir/.env` on the Droplet (or in `PROD_ENV_FILE`).

### Privacy and object storage
Keep the R2 bucket private. Omit `R2_PUBLIC_BASE_URL` so the API issues short-lived presigned GET URLs.

### Example `/opt/mir/.env`
```env
DOMAIN=api.yourdomain.com
TAG=latest
DATABASE_URL=postgresql+psycopg://postgres.mghlumhhbjfeqvnmqrjs:<PASSWORD>@aws-0-eu-west-3.pooler.supabase.com:5432/postgres
REDIS_URL=redis://redis:6379/0
R2_ENDPOINT=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
R2_BUCKET=music-info-retrieval-research-1
R2_ACCESS_KEY_ID=<R2_KEY>
R2_SECRET_ACCESS_KEY=<R2_SECRET>
SUPABASE_JWKS_URL=https://mghlumhhbjfeqvnmqrjs.supabase.co/auth/v1/.well-known/jwks.json
CORS_ORIGIN_REGEX=^https:\/\/(.*\.)?(lovable\.app|lovableproject\.com|pages\.dev|novice-coder\.workers\.dev)$
MAX_UPLOAD_MB=100
ALLOW_PLACEHOLDER_STEMS=0
```

**Quote values that contain shell metacharacters.** Single-quote `CORS_ORIGIN_REGEX` on the Droplet file if you edit it by hand.
