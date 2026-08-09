"""Object-storage adapter: Cloudflare R2 (S3-compatible) with a local fallback.

Active backend selection (AD-2):

* **r2**    - used when ``R2_ENDPOINT``/``R2_ACCOUNT_ID``, ``R2_BUCKET`` and the
  access credentials are configured AND boto3 is importable.
* **local** - used otherwise (or when an R2 upload fails): the file is already
  in the ``backend/uploads`` tree, served by the existing ``/uploads`` mount.

The adapter always reports the backend it actually used (``storage_backend`` +
stable URL), so the platform never claims R2 persistence ran when it did not
(Story 2.3 AC-5).
"""

import os
from pathlib import Path
from typing import Optional

try:
    import boto3
    from botocore.config import Config

    BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover - optional-dependency degraded mode
    boto3 = None  # type: ignore[assignment]
    Config = None  # type: ignore[assignment]
    BOTO3_AVAILABLE = False

_R2_ENDPOINT_SUFFIX = '.r2.cloudflarestorage.com'


def get_r2_settings() -> Optional[dict]:
    """Return R2 settings when fully configured, else None."""
    account_id = os.environ.get('R2_ACCOUNT_ID', '').strip()
    endpoint = os.environ.get('R2_ENDPOINT', '').strip()
    if not endpoint and account_id:
        endpoint = f'https://{account_id}{_R2_ENDPOINT_SUFFIX}'
    bucket = os.environ.get('R2_BUCKET', '').strip()
    access_key_id = os.environ.get('R2_ACCESS_KEY_ID', '').strip()
    secret_access_key = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip()
    if not (endpoint and bucket and access_key_id and secret_access_key):
        return None
    return {
        'endpoint': endpoint,
        'bucket': bucket,
        'access_key_id': access_key_id,
        'secret_access_key': secret_access_key,
        'public_base_url': os.environ.get('R2_PUBLIC_BASE_URL', '').strip() or None,
    }


def active_backend() -> str:
    """Return the object-storage backend currently in effect: 'r2' or 'local'."""
    if BOTO3_AVAILABLE and get_r2_settings() is not None:
        return 'r2'
    return 'local'


def mirror_file(*, local_path: Path, object_key: str, content_type: Optional[str], local_url: str) -> dict:
    """Make the file available through the active backend and return its URL.

    * r2: uploads the bytes under ``object_key`` and returns a stable URL.
    * local: the file is already served by ``local_url`` under /uploads.

    On any R2 failure the adapter degrades to the local URL and records
    ``storage_backend='local'`` (honest degradation, never a hard failure).
    """
    if active_backend() == 'r2':
        try:
            url = _upload_to_r2(get_r2_settings(), Path(local_path), object_key, content_type)
            return {'url': url, 'storage_backend': 'r2', 'key': object_key}
        except Exception:
            pass
    return {'url': local_url, 'storage_backend': 'local', 'key': None}


def _upload_to_r2(settings: dict, local_path: Path, object_key: str, content_type: Optional[str]) -> str:
    """Upload a local file to the R2 bucket; returns its stable public URL."""
    client = boto3.client(
        's3',
        endpoint_url=settings['endpoint'],
        region_name='auto',
        aws_access_key_id=settings['access_key_id'],
        aws_secret_access_key=settings['secret_access_key'],
        config=Config(signature_version='s3v4'),
    )
    with open(local_path, 'rb') as source:
        client.put_object(
            Bucket=settings['bucket'],
            Key=object_key,
            Body=source,
            ContentType=content_type or 'application/octet-stream',
        )
    base = settings.get('public_base_url')
    if base:
        return f'{base.rstrip("/")}/{object_key}'
    return f"{settings['endpoint']}/{settings['bucket']}/{object_key}"