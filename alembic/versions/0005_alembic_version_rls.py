"""Enable RLS on public.alembic_version (no policies)

Revision ID: 0005_alembic_version_rls
Revises: 0004_upload_intents
Create Date: 2026-11-15

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0005_alembic_version_rls'
down_revision = '0004_upload_intents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded like 0003: only when the auth schema exists so CI on plain Postgres passes.
    # No policies — service role / migration path remains unrestricted; anon/authenticated
    # clients cannot read or write alembic_version via PostgREST.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                IF EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'alembic_version'
                ) THEN
                    EXECUTE 'ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY';
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
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'alembic_version'
                ) THEN
                    EXECUTE 'ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY';
                END IF;
            END IF;
        END $$;
        """
    )
