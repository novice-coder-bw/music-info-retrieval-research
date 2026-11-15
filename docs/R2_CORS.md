# Cloudflare R2 CORS Configuration

To allow direct browser uploads via presigned URLs and playback from Lovable / Cloudflare Worker clients, configure CORS on the `music-info-retrieval-research-1` bucket in the Cloudflare Dashboard (R2 → Settings → CORS Policy).

```json
[
  {
    "AllowedOrigins": [
      "https://mirr-web.novice-coder.workers.dev",
      "https://*.lovable.app",
      "https://*.lovableproject.com",
      "https://*.pages.dev",
      "http://localhost:5173",
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
      "Content-Length",
      "Content-Range",
      "Accept-Ranges"
    ],
    "MaxAgeSeconds": 3600
  }
]
```

Notes:
- Production Worker origin is listed explicitly; preview Workers use `https://<prefix>-mirr-web.novice-coder.workers.dev` (add specific preview origins if wildcards are insufficient for your account).
- `PUT` is required for presigned client uploads; `GET`/`HEAD` for playback and size checks.
