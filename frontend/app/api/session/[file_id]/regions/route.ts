import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

// Proxy region selections to the backend session resource. Keeping the browser
// same-origin avoids CORS and reuses the established proxy-route pattern.
export async function POST(req: NextRequest, { params }: { params: Promise<{ file_id: string }> }) {
  const { file_id } = await params;
  const body = await req.json();

  const response = await fetch(`${BACKEND_URL}/api/regions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ file_id, ...body }),
  });

  const responseBody = await response.arrayBuffer();
  const headers = new Headers();
  const contentType = response.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }

  return new NextResponse(responseBody, {
    status: response.status,
    headers,
  });
}