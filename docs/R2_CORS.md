# Cloudflare R2 CORS Configuration

To allow direct browser uploads via presigned URLs and playback from Lovable / web clients, configure CORS on the `music-info-retrieval-research-1` bucket in the Cloudflare Dashboard (R2 -> Settings -> CORS Policy).

```json
[
  {
    "AllowedOrigins": [
      "https://*.lovable.app",
      "https://*.lovableproject.com",
      "https://*.pages.dev",
      "https://mirr-web.novice-coder.workers.dev",
      "https://*-mirr-web.novice-coder.workers.dev",
      "http://localhost:3000"
    ],
    "AllowedMethods": [
      "GET",
      "PUT",
      "HEAD"
    ],
    "AllowedHeaders": [
      "*"
    ],
    "ExposeHeaders": [
      "ETag",
      "Content-Type",
      "Content-Length"
    ],
    "MaxAgeSeconds": 3600
  }
]
```

`https://mirr-web.novice-coder.workers.dev` is the production frontend and `https://*-mirr-web.novice-coder.workers.dev` covers its preview deployments (see "Frontend origins" in `docs/RUNBOOK.md`). Cloudflare's R2 CORS documentation only shows exact origins; if a wildcard origin is not honoured, add each preview origin explicitly.
