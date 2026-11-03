"""Alembic environment for the Music Analysis Platform durable store.

The migration URL is resolved from the DATABASE_URL environment variable
(Neon Postgres in production). When it is unset, a local SQLite file is used
so the migration can be exercised offline (``alembic upgrade head``).
"""

from logging.config import fileConfig
from pathlib import Path
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / '.env')
except Exception:  # pragma: no cover - optional convenience loader
    pass

from db.engine import normalize_database_url  # noqa: E402
from db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = (
    os.environ.get('DATABASE_URL', '').strip()
    or config.get_main_option('sqlalchemy.url')
)
# Apply the same psycopg (v3) driver rewrite the app engine uses so a bare
# 'postgresql://...' DATABASE_URL (as documented in .env.example) resolves to
# the installed driver instead of the missing psycopg2.
database_url = normalize_database_url(database_url)
config.set_main_option('sqlalchemy.url', database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a live engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()