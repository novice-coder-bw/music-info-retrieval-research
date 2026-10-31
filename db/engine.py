import os
from typing import Optional
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

_engine: Optional[Engine] = None


def normalize_database_url(url: str) -> str:
    """Normalize Postgres URLs to use psycopg (v3) or preserve psycopg2 if explicitly given."""
    if not url:
        return ''
    if url.startswith('sqlite'):
        raise RuntimeError('SQLite is not supported. Use Supabase PostgreSQL with DATABASE_URL.')
    # If starting with postgres:// or bare postgresql://, translate to postgresql+psycopg://
    if url.startswith('postgres://'):
        return 'postgresql+psycopg://' + url.split('://', 1)[1]
    if url.startswith('postgresql://'):
        return 'postgresql+psycopg://' + url.split('://', 1)[1]
    return url


def get_database_url() -> str:
    """Return the configured DATABASE_URL or raise RuntimeError."""
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        raise RuntimeError('DATABASE_URL environment variable is required.')
    if url.startswith('sqlite'):
        raise RuntimeError('SQLite is not supported. Use Supabase PostgreSQL with DATABASE_URL.')
    return normalize_database_url(url)


def create_engine_for_url(url: str) -> Engine:
    """Create an engine with Supabase pool and timeout settings."""
    normalized = normalize_database_url(url)
    connect_args = {
        'sslmode': 'require',
        'connect_timeout': 10,
    }
    # Note: create_engine is lazy and does not establish a connection at import time
    return create_engine(
        normalized,
        pool_size=3,
        max_overflow=2,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )


def get_engine() -> Engine:
    """Return the cached application engine, initializing lazily without connecting."""
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_engine_for_url(url)
    return _engine


def reset_engine() -> None:
    """Dispose and clear cached engine."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session_factory() -> sessionmaker:
    """Return a sessionmaker bound to the application engine."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
