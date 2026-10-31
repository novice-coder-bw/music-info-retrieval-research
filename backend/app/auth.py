import logging
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import PyJWKClient

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_jwks_client: Optional[PyJWKClient] = None


def get_jwks_client() -> PyJWKClient:
    """Return a cached PyJWKClient for Supabase JWKS."""
    global _jwks_client
    if _jwks_client is None:
        jwks_url = os.environ.get('SUPABASE_JWKS_URL', '').strip()
        if not jwks_url:
            project_ref = os.environ.get('SUPABASE_PROJECT_REF', 'mghlumhhbjfeqvnmqrjs').strip()
            jwks_url = f'https://{project_ref}.supabase.co/auth/v1/.well-known/jwks.json'
        _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


def get_current_user_id(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Validate Supabase JWT and return the sub (user_id).

    Validates RS256/ES256, audience='authenticated'.
    Tests can override this dependency using app.dependency_overrides[get_current_user_id].
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Authentication credentials were not provided',
            headers={'WWW-Authenticate': 'Bearer'},
        )

    token = credentials.credentials
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['RS256', 'ES256'],
            audience='authenticated',
            options={'verify_aud': True},
        )
        user_id = payload.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='Token missing sub claim',
                headers={'WWW-Authenticate': 'Bearer'},
            )
        return str(user_id)
    except jwt.PyJWTError as exc:
        logger.warning('JWT validation error: %s', exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f'Invalid authentication token: {exc}',
            headers={'WWW-Authenticate': 'Bearer'},
        ) from exc
