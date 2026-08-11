import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? 'http://localhost:8000';

export async function GET(_req: NextRequest, { params }: { params: Promise<{ file_id: string }> }) {
  const { file_id } = await params;
  const response = await fetch(`${BACKEND_URL}/api/session/${encodeURIComponent(file_id)}`, {
    method: 'GET',
    headers: { accept: 'application/json' },
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
