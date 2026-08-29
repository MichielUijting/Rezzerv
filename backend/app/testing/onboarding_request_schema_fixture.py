from __future__ import annotations

from sqlalchemy import text


def install_household_onboarding_schema(conn) -> None:
    """Install the Alembic-owned onboarding contract for isolated SQLite selftests."""
    conn.execute(text("""
        CREATE TABLE household_onboarding (
            household_id TEXT PRIMARY KEY,
            onboarding_status TEXT NOT NULL
                CHECK (onboarding_status IN ('not_started', 'in_progress', 'completed')),
            onboarding_version INTEGER NOT NULL DEFAULT 2,
            primary_use_case TEXT
                CHECK (
                    primary_use_case IS NULL
                    OR primary_use_case IN ('inhuis_halen', 'wat_inhuis', 'waar_inhuis')
                ),
            onboarding_step TEXT,
            household_usage_mode TEXT
                CHECK (
                    household_usage_mode IS NULL
                    OR household_usage_mode IN ('alone', 'together')
                ),
            onboarding_completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))


def backfill_completed_household_onboarding(conn) -> None:
    """Mirror revision 20260829_03's existing-household data backfill in tests."""
    conn.execute(text("""
        INSERT INTO household_onboarding (
            household_id,
            onboarding_status,
            onboarding_version,
            primary_use_case,
            onboarding_step,
            household_usage_mode,
            onboarding_completed_at,
            created_at,
            updated_at
        )
        SELECT
            CAST(id AS TEXT),
            'completed',
            2,
            NULL,
            NULL,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM household_registry
        WHERE lower(trim(COALESCE(context_type, 'regular'))) = 'regular'
          AND NOT EXISTS (
              SELECT 1
              FROM household_onboarding ho
              WHERE ho.household_id = CAST(household_registry.id AS TEXT)
          )
    """))


def install_household_product_configuration_schema(conn) -> None:
    """Install revision 20260829_06's product-configuration contract for tests."""
    conn.execute(text("""
        CREATE TABLE household_product_configuration (
            household_id TEXT PRIMARY KEY,
            inventory_tracking_level TEXT NOT NULL
                CHECK (inventory_tracking_level IN ('none', 'presence', 'quantity')),
            location_tracking_level TEXT NOT NULL
                CHECK (location_tracking_level IN ('none', 'global', 'exact')),
            shopping_enabled INTEGER NOT NULL DEFAULT 0 CHECK (shopping_enabled IN (0, 1)),
            almost_out_enabled INTEGER NOT NULL DEFAULT 0 CHECK (almost_out_enabled IN (0, 1)),
            almost_out_notifications_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (almost_out_notifications_enabled IN (0, 1)),
            receipt_processing_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (receipt_processing_enabled IN (0, 1)),
            recipes_enabled INTEGER NOT NULL DEFAULT 0 CHECK (recipes_enabled IN (0, 1)),
            unpacking_enabled INTEGER NOT NULL DEFAULT 0 CHECK (unpacking_enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))


def install_location_schema(conn) -> None:
    """Install the revision 03/06 location contract for isolated SQLite selftests."""
    conn.execute(text("""
        CREATE TABLE spaces (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            household_id TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            is_direct INTEGER NOT NULL DEFAULT 0
        )
    """))
    conn.execute(text("""
        CREATE TABLE sublocations (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            space_id TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX ux_spaces_household_direct
        ON spaces(household_id)
        WHERE is_direct = 1
    """))
    conn.execute(text("""
        CREATE TRIGGER trg_spaces_direct_immutable_update
        BEFORE UPDATE OF naam, active ON spaces
        FOR EACH ROW
        WHEN OLD.is_direct = 1
          AND (
            lower(trim(COALESCE(NEW.naam, ''))) <> 'direct'
            OR COALESCE(NEW.active, 1) <> 1
          )
        BEGIN
            SELECT RAISE(ABORT, 'Direct is een vaste locatie');
        END
    """))
    conn.execute(text("""
        CREATE TRIGGER trg_spaces_direct_immutable_delete
        BEFORE DELETE ON spaces
        FOR EACH ROW
        WHEN OLD.is_direct = 1
        BEGIN
            SELECT RAISE(ABORT, 'Direct is een vaste locatie');
        END
    """))
