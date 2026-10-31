"""create sessions and artifacts tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sessions',
        sa.Column('file_id', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=256), nullable=True),
        sa.Column('content_type', sa.String(length=128), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('artifact_url', sa.Text(), nullable=True),
        sa.Column('analysis', sa.JSON(), nullable=True),
        sa.Column('stems', sa.JSON(), nullable=True),
        sa.Column('workflow_stages', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('file_id'),
    )
    op.create_table(
        'artifacts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('storage_backend', sa.String(length=16), nullable=False),
        sa.Column('key', sa.Text(), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('format', sa.String(length=32), nullable=True),
        sa.Column('mime_type', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_artifacts_file_id'), 'artifacts', ['file_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_artifacts_file_id'), table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_table('sessions')
