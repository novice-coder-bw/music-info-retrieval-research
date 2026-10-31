#!/usr/bin/env python3
"""Export FastAPI OpenAPI JSON schema with dummy environment variables set.

Can run offline without connecting to PostgreSQL or R2.
"""

import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Dummy environment variables to allow clean imports
os.environ.setdefault('DATABASE_URL', 'postgresql+psycopg://dummy:dummy@localhost:5432/dummy')
os.environ.setdefault('R2_ENDPOINT', 'https://dummy.r2.cloudflarestorage.com')
os.environ.setdefault('R2_BUCKET', 'music-info-retrieval-research-1')
os.environ.setdefault('R2_ACCESS_KEY_ID', 'dummy_key')
os.environ.setdefault('R2_SECRET_ACCESS_KEY', 'dummy_secret')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('SUPABASE_JWKS_URL', 'https://mghlumhhbjfeqvnmqrjs.supabase.co/auth/v1/.well-known/jwks.json')

from backend.app.main import app


def main():
    openapi_schema = app.openapi()
    out_path = ROOT_DIR / 'openapi.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(openapi_schema, f, indent=2)
    print(f'Wrote OpenAPI specification to {out_path}')


if __name__ == '__main__':
    main()
