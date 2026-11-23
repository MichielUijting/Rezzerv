"""Allow canonical Direct-space deletion only inside explicit full-household resets.

Revision ID: 20261123_01
Revises: 20261121_01

The Direct-location row remains immutable for all normal DELETE/UPDATE routes.
Only the authorized reset service can open a transaction-local, target-scoped
exception for the exact DELETE statement that removes the entire household.
No existing household rows are modified by this migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261123_01"
down_revision = "20261121_01"
branch_labels = None
depends_on = None
CI_IMPACT_DOMAINS = ["auth", "platform", "shared", "inventory", "receipt"]


def _replace_guard(*, allow_full_reset: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # The canonical trigger is installed by revision 20260829_06.
    # Never weaken protections if it is absent or the schema is inconsistent.
    count = int(bind.execute(sa.text("""
        SELECT COUNT(*)
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relname = 'spaces'
          AND t.tgname = 'trg_spaces_direct_immutable_delete'
          AND NOT t.tgisinternal
    """)).scalar_one())
    if count != 1:
        raise RuntimeError("Direct-location DELETE guard missing; migration stopped")

    permitted_delete = (
        """
            IF current_setting('inhuis.household_reset_target', true)
                   = OLD.household_id::text THEN
                RETURN OLD;
            END IF;
        """
        if allow_full_reset else ""
    )

    bind.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION rezzerv_spaces_direct_immutable_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $guard$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                {permitted_delete}
                RAISE EXCEPTION 'Direct is een vaste locatie';
            END IF;
            IF lower(trim(COALESCE(NEW.naam, ''))) <> 'direct'
               OR lower(COALESCE(NEW.active::text, 'true'))
                  NOT IN ('1', 't', 'true') THEN
                RAISE EXCEPTION 'Direct is een vaste locatie';
            END IF;
            RETURN NEW;
        END;
        $guard$
    """))


def upgrade() -> None:
    _replace_guard(allow_full_reset=True)


def downgrade() -> None:
    _replace_guard(allow_full_reset=False)
