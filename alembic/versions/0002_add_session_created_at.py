"""add created_at to sessions

Revision ID: 0002_add_session_created_at
Revises: 0001_initial
Create Date: 2026-08-11

The sessions table already gained a created_at column in the model/store so the
persisted session dict mirrors the in-memory SESSIONS contract (which includes
created_at). This migration adds the column to databases already migrated with
0001_initial (e.g. Neon Postgres). Idempotent create_all in db/engine only adds
missing tables, not columns, so an explicit migration is required.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_session_created_at'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('created_at', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'created_at')
