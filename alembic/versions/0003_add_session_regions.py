"""add regions to sessions

Revision ID: 0003_add_session_regions
Revises: 0002_add_session_created_at
Create Date: 2026-08-16

The sessions table already gained a regions column in the model/store so the
persisted session dict mirrors the in-memory SESSIONS contract (which includes
the user's selected time regions). This migration adds the column to databases
already migrated with 0002. Idempotent create_all in db/engine only adds missing
tables, not columns, so an explicit migration is required.

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_session_regions'
down_revision = '0002_add_session_created_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sessions', sa.Column('regions', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'regions')