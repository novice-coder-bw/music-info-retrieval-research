"""Alembic environment for the Music Analysis Platform durable store.

Reads DATABASE_URL from environment (Supabase Postgres), ignores Supabase-managed
schemas (auth, storage, realtime, extensions, vault), and compares only the public schema.
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
except Exception:
    pass

from db.engine import normalize_database_url  # noqa: E402
from db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get('DATABASE_URL', '').strip() or config.get_main_option('sqlalchemy.url')
if not database_url:
    raise RuntimeError('DATABASE_URL is required for Alembic migrations.')

database_url = normalize_database_url(database_url)
config.set_main_option('sqlalchemy.url', database_url)

target_metadata = Base.metadata

IGNORED_SCHEMAS = {'auth', 'storage', 'realtime', 'extensions', 'vault', 'pg_catalog', 'information_schema'}


def include_object(object, name, type_, reflected, compare_to):
    """Only include objects in the public schema, ignoring Supabase-managed schemas."""
    schema = getattr(object, 'schema', None)
    if schema in IGNORED_SCHEMAS:
        return False
    if type_ == 'table' and schema not in (None, 'public'):
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        include_schemas=False,
        include_object=include_object,
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
            include_schemas=False,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
