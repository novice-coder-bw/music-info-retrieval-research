import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const body = await req.json();
  const response = await fetch(`${BACKEND_URL}/api/analyze`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
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
