"""enable row level security on alembic_version

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
    # No policies: Alembic and the API connect as postgres, which bypasses RLS;
    # Supabase's anon/authenticated roles get no rows through the Data API.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
                EXECUTE 'ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY';
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
                EXECUTE 'ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY';
            END IF;
        END $$;
        """
    )
