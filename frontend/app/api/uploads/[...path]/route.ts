import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

// Proxy static audio artifacts (stems / uploads) served by the backend's
// `/uploads` mount. Keeping the browser same-origin avoids CORS and lets
// WaveSurfer decode the audio fetched through this route.
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const safePath = path.map(encodeURIComponent).join('/');

  // Forward Range headers so the backend's StaticFiles mount can answer with
  // partial content (206). WaveSurfer v7 fetches the whole blob regardless, but
  // any future/progressive loader (or browser preloads) benefits from range
  // support, and it lets the response body start flowing to the client sooner.
  const range = req.headers.get('range');
  const accept = req.headers.get('accept');
  const upstreamHeaders: Record<string, string> = {};
  if (accept) upstreamHeaders['accept'] = accept;
  if (range) upstreamHeaders['range'] = range;

  const response = await fetch(`${BACKEND_URL}/uploads/${safePath}`, {
    method: 'GET',
    // Stems are immutable once generated, but keep the upstream call uncached
    // so a regenerated stem is never served stale from this server's cache.
    cache: 'no-store',
    headers: upstreamHeaders,
  });

  const headers = new Headers();
  const contentType = response.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }
  const contentLength = response.headers.get('content-length');
  if (contentLength) {
    headers.set('content-length', contentLength);
  }
  const contentRange = response.headers.get('content-range');
  if (contentRange) {
    headers.set('content-range', contentRange);
  }
  const acceptRanges = response.headers.get('accept-ranges');
  if (acceptRanges) {
    headers.set('accept-ranges', acceptRanges);
  }
  // Stem artifacts are immutable once written, so allow the browser to cache
  // them. Re-visiting the timeline (or re-selecting a stem) will then be served
  // from the HTTP cache instead of re-fetching across the proxy hop.
  headers.set('cache-control', 'public, max-age=3153603, immutable');

  // Stream the body through instead of eagerly buffering the entire file into
  // server memory via `response.arrayBuffer()`. This removes a full in-memory
  // copy of every stem on this server and lets the client begin receiving
  // bytes while the backend is still transferring the rest.
  return new NextResponse(response.body, {
    status: response.status,
    headers,
  });
}
