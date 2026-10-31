import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except Exception:
    pass

import boto3
from botocore.config import Config


def get_r2_settings() -> dict:
    """Return R2 settings or raise RuntimeError if missing required env vars."""
    endpoint = os.environ.get('R2_ENDPOINT', '').strip()
    bucket = os.environ.get('R2_BUCKET', '').strip()
    access_key_id = os.environ.get('R2_ACCESS_KEY_ID', '').strip()
    secret_access_key = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip()

    missing = []
    if not endpoint:
        missing.append('R2_ENDPOINT')
    if not bucket:
        missing.append('R2_BUCKET')
    if not access_key_id:
        missing.append('R2_ACCESS_KEY_ID')
    if not secret_access_key:
        missing.append('R2_SECRET_ACCESS_KEY')

    if missing:
        raise RuntimeError(f"Missing required Cloudflare R2 environment variables: {', '.join(missing)}")

    return {
        'endpoint': endpoint,
        'bucket': bucket,
        'access_key_id': access_key_id,
        'secret_access_key': secret_access_key,
        'public_base_url': os.environ.get('R2_PUBLIC_BASE_URL', '').strip() or None,
    }


def get_s3_client():
    """Return configured boto3 S3 client for Cloudflare R2."""
    settings = get_r2_settings()
    endpoint = settings['endpoint']
    kwargs = {
        'service_name': 's3',
        'aws_access_key_id': settings['access_key_id'],
        'aws_secret_access_key': settings['secret_access_key'],
    }
    if endpoint and not endpoint.startswith('mock://'):
        kwargs['endpoint_url'] = endpoint
        kwargs['region_name'] = 'auto'
        kwargs['config'] = Config(signature_version='s3v4')
    else:
        kwargs['region_name'] = 'us-east-1'
    return boto3.client(**kwargs)


def upload_file(*, local_path: Path, object_key: str, content_type: Optional[str] = None) -> dict:
    """Upload a local file directly to Cloudflare R2."""
    settings = get_r2_settings()
    client = get_s3_client()
    with open(local_path, 'rb') as source:
        client.put_object(
            Bucket=settings['bucket'],
            Key=object_key,
            Body=source,
            ContentType=content_type or 'application/octet-stream',
        )

    base = settings.get('public_base_url')
    if base:
        url = f"{base.rstrip('/')}/{object_key}"
    else:
        url = f"{settings['endpoint'].rstrip('/')}/{settings['bucket']}/{object_key}"

    return {
        'url': url,
        'storage_backend': 'r2',
        'key': object_key,
    }


def generate_presigned_put_url(*, object_key: str, content_type: str, expires_in: int = 3600) -> str:
    """Generate a presigned PUT URL for direct client upload to Cloudflare R2."""
    settings = get_r2_settings()
    client = get_s3_client()
    url = client.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': settings['bucket'],
            'Key': object_key,
            'ContentType': content_type,
        },
        ExpiresIn=expires_in,
    )
    return url


def get_public_url(object_key: str) -> str:
    """Get public URL for an R2 object."""
    settings = get_r2_settings()
    base = settings.get('public_base_url')
    if base:
        return f"{base.rstrip('/')}/{object_key}"
    return f"{settings['endpoint'].rstrip('/')}/{settings['bucket']}/{object_key}"
