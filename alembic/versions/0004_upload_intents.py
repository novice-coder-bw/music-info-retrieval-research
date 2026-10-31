"""create upload_intents table to track presigned upload issuance

Revision ID: 0004_upload_intents
Revises: 0003_supabase_security_realtime
Create Date: 2026-10-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_upload_intents'
down_revision = '0003_supabase_security_realtime'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'upload_intents',
        sa.Column('object_key', sa.String(length=256), primary_key=True),
        sa.Column('file_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('expected_content_type', sa.String(length=128), nullable=False),
        sa.Column('expected_max_size', sa.Integer(), nullable=False),
        sa.Column('completed', sa.Boolean(), default=False, nullable=False),
        sa.Column('created_at', sa.String(length=64), nullable=False),
    )
    op.create_index(op.f('ix_upload_intents_user_id'), 'upload_intents', ['user_id'], unique=False)

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                EXECUTE 'ALTER TABLE public.upload_intents ENABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_upload_intents_user_id'), table_name='upload_intents')
    op.drop_table('upload_intents')
