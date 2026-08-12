"""SQLAlchemy engine + session factory for the durable store (AD-2).

Reads ``DATABASE_URL`` (Neon Postgres) from the environment and falls back to
an in-memory SQLite store when it is unset, mirroring the local degraded-mode
behavior used everywhere else (Celery -> in-process, Demucs -> placeholder).
"""

import logging
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
except Exception:  # pragma: no cover - dotenv is an optional convenience loader
    pass

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None


def normalize_database_url(url: str) -> str:
    """Rewrite a bare ``postgresql://`` URL onto the installed psycopg (v3) driver.

    SQLAlchemy maps a bare ``postgresql://`` to the psycopg2 dialect, which is NOT
    installed and fails at runtime with "No module named 'psycopg2'". The backend
    installs psycopg (v3), so rewrite to ``postgresql+psycopg://``. Shared with the
    alembic migration entrypoint so the app engine and the migration tool resolve
    the same dialect for the same ``DATABASE_URL``.
    """
    url = (url or '').strip()
    if not url:
        return url
    if url.startswith('postgresql://') or url.startswith('postgres://'):
        return 'postgresql+psycopg://' + url.split('://', 1)[1]
    return url


def get_database_url() -> str:
    """Return the configured database URL, or the local SQLite fallback."""
    url = os.environ.get('DATABASE_URL') or ''
    if not url.strip():
        return 'sqlite:///:memory:'
    return normalize_database_url(url)


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
    # Bound the connect attempt so an unreachable Postgres degrades to the local
    # store quickly instead of blocking a request for the driver's default time.
    return create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 8})


def _build_engine() -> Engine:
    """Build the engine, degrading to the local store when Postgres is unusable.

    Mirrors the project-wide degraded-mode convention (Celery -> in-process,
    Demucs -> placeholder): if the configured Postgres is unreachable/misconfigured
    the app still boots and persists to an in-memory SQLite store instead of
    raising or silently dropping writes.
    """
    url = get_database_url()
    if url.startswith('sqlite'):
        engine = create_engine_for_url(url)
        Base.metadata.create_all(engine)  # idempotent: only creates missing tables
    else:
        candidate = create_engine_for_url(url)
        try:
            with candidate.connect():  # confirm the configured DB is reachable
                pass
            # Postgres schema is version-controlled by alembic (db/ migrations
            # 0001/0002); do NOT create_all here or `alembic upgrade head` will
            # fail on already-existing tables/columns. A reachable-but-unmigrated
            # database is NOT usable: every persist would fail with UndefinedTable
            # while the platform believes it is durable, so detect the missing
            # schema and degrade honestly (with an actionable warning).
            inspector = inspect(candidate)
            if inspector.has_table('sessions') and inspector.has_table('artifacts'):
                engine = candidate
            else:
                candidate.dispose()
                logger.warning(
                    'Postgres store is reachable but missing the sessions/artifacts tables — '
                    'run `alembic upgrade head` against DATABASE_URL; degrading to in-memory '
                    'SQLite (session metadata will NOT survive a restart)',
                )
                engine = create_engine_for_url('sqlite:///:memory:')
                Base.metadata.create_all(engine)
        except Exception as exc:
            candidate.dispose()
            logger.warning(
                'Postgres store unreachable (%s); degrading to in-memory SQLite — '
                'session metadata will NOT survive a restart', exc,
            )
            engine = create_engine_for_url('sqlite:///:memory:')
            Base.metadata.create_all(engine)
    return engine


def get_engine() -> Engine:
    """Lazily build (and retain) the application engine + tables."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def configure_engine(url: str) -> Engine:
    """Point the application store at a specific engine URL (used by tests)."""
    global _engine
    _engine = create_engine_for_url(url)
    if url.startswith('sqlite'):
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