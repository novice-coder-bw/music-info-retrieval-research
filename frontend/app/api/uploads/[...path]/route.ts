import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

// Proxy static audio artifacts (stems / uploads) served by the backend's
// `/uploads` mount. Keeping the browser same-origin avoids CORS and lets
// WaveSurfer decode the audio fetched through this route.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const safePath = path.map(encodeURIComponent).join('/');
  const response = await fetch(`${BACKEND_URL}/uploads/${safePath}`, {
    method: 'GET',
    cache: 'no-store',
  });

  const responseBody = await response.arrayBuffer();
  const headers = new Headers();
  const contentType = response.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }
  const contentLength = response.headers.get('content-length');
  if (contentLength) {
    headers.set('content-length', contentLength);
  }

  return new NextResponse(responseBody, {
    status: response.status,
    headers,
  });
}
