"""add user_id to sessions and configure supabase security and realtime

Revision ID: 0003_supabase_security_realtime
Revises: 0002_add_session_created_at
Create Date: 2026-10-31

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_supabase_security_realtime'
down_revision = '0002_add_session_created_at'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add nullable uuid user_id column to sessions table (no foreign key)
    op.add_column('sessions', sa.Column('user_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)

    # 2. Inside a DO $$ block that checks the auth schema exists (so CI on plain Postgres still passes):
    # - ENABLE ROW LEVEL SECURITY on every public table
    # - create a SELECT policy "owner_read" on sessions with USING (user_id = auth.uid())
    # - if the publication supabase_realtime exists, ALTER PUBLICATION supabase_realtime ADD TABLE public.sessions
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                -- Enable RLS on public tables
                EXECUTE 'ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY';
                EXECUTE 'ALTER TABLE public.artifacts ENABLE ROW LEVEL SECURITY';

                -- Drop policy if exists and create owner_read policy on sessions
                IF EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'sessions' AND policyname = 'owner_read'
                ) THEN
                    EXECUTE 'DROP POLICY owner_read ON public.sessions';
                END IF;

                EXECUTE 'CREATE POLICY owner_read ON public.sessions FOR SELECT USING (user_id::text = auth.uid()::text)';

                -- Add sessions table to supabase_realtime publication if publication exists
                IF EXISTS (
                    SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'
                ) THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_publication_tables
                        WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'sessions'
                    ) THEN
                        EXECUTE 'ALTER PUBLICATION supabase_realtime ADD TABLE public.sessions';
                    END IF;
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                IF EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = 'sessions' AND policyname = 'owner_read'
                ) THEN
                    EXECUTE 'DROP POLICY owner_read ON public.sessions';
                END IF;
            END IF;
        END $$;
        """
    )
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_column('sessions', 'user_id')
