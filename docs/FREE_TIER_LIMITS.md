# Free-Tier Limits and Retention Guidelines

This document tracks free-tier constraints and limits across all connected services, helping maintain service uptime and prevent unexpected billing or service suspension.

---

## 1. Supabase Free Tier

- **Project Inactivity Pause**:
  - Automatically pauses after **7 days** of database inactivity.
  - *Mitigation*: The `keepalive.yml` GitHub Actions workflow runs every 3 days at 00:00 UTC, pinging `/health` (which runs `SELECT 1` on Supabase Postgres).
- **Database Size Limit**:
  - **500 MB** disk size limit.
- **File Storage Limit**:
  - **1 GB** file storage. (Audio uploads and stems bypass Supabase storage and are stored in Cloudflare R2).
- **Egress Limit**:
  - **5 GB** per month.
- **Projects**:
  - Up to 2 active free projects.
- **Backups**:
  - No daily automated backups on the free tier.
  - *Mitigation*: The `backup-db.yml` workflow runs `pg_dump` weekly, encrypts the dump with AES-256-CBC, and stores it in Cloudflare R2 (`backups/`) with an 8-week retention window.

---

## 2. Jules (Coding Agent)

- **Daily Tasks**: 15 tasks per day [verify].
- **Concurrency**: 3 concurrent tasks [verify].

---

## 3. Lovable Free Tier

- **Daily Credits**: 5 credits per day [verify].
- **Monthly Credits**: 30 credits per month [verify].

---

## 4. Cloudflare R2 Object Storage

- **Class A Operations** (writes/lists): 1,000,000 requests/month free.
- **Class B Operations** (reads): 10,000,000 requests/month free.
- **Storage**: 10 GB free per month.
- **Egress**: Free (no bandwidth egress charges).
- **Lifecycle Rule Recommendation**:
  - To prevent old stem files and uploaded tracks from exceeding storage capacity, configure a Lifecycle Rule in Cloudflare R2:
    - Prefix: `uploads/` -> Expire objects after 30 days.
    - Prefix: `stems/` -> Expire objects after 30 days.
    - Prefix: `backups/` -> Handled by `backup-db.yml` (prunes files older than 56 days / 8 weeks).

---

## 5. GitHub Actions (Public Repository)

- **Execution Minutes**: Unlimited standard runner minutes for public open-source repositories.
- **Public Artifacts & Logs**:
  - Actions logs are public. **Never log secrets, tokens, or IP addresses.**
  - Never upload database dumps as public GitHub artifacts.
- **Workflow Inactivity**:
  - Scheduled workflows (`cron`) may be automatically disabled by GitHub after 60 days of inactivity on the repository. Pushing commits or triggering workflows manually resets the timer.
