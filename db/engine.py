"""SQLAlchemy engine + session factory for the durable store (AD-2).

Reads ``DATABASE_URL`` (Neon Postgres) from the environment and falls back to
an in-memory SQLite store when it is unset, mirroring the local degraded-mode
behavior used everywhere else (Celery -> in-process, Demucs -> placeholder).
"""

import os
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base

_engine: Optional[Engine] = None


def get_database_url() -> str:
    """Return the configured database URL, or the local SQLite fallback."""
    url = os.environ.get('DATABASE_URL') or ''
    url = url.strip()
    if url:
        return url
    return 'sqlite:///:memory:'


def create_engine_for_url(url: str) -> Engine:
    """Create an engine, adding the flags SQLite needs for threads/local runs."""
    if url.startswith('sqlite'):
        if url == 'sqlite://':
            url = 'sqlite:///:memory:'
        return create_engine(
            url,
            connect_args={'check_same_thread': False},
            # One shared in-memory database for the whole process (default
            # fallback mode); file-based URLs work identically for tests.
            poolclass=StaticPool,
        )
    return create_engine(url, pool_pre_ping=True)


def get_engine() -> Engine:
    """Lazily build (and retain) the application engine + tables."""
    global _engine
    if _engine is None:
        _engine = create_engine_for_url(get_database_url())
        Base.metadata.create_all(_engine)  # idempotent: only creates missing tables
    return _engine


def configure_engine(url: str) -> Engine:
    """Point the application store at a specific engine URL (used by tests)."""
    global _engine
    _engine = create_engine_for_url(url)
    Base.metadata.create_all(_engine)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine so the next call rebuilds it (used by tests)."""
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