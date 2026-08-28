"""Test-only SQLite receipt lifecycle contract helpers.

Production schema authority belongs exclusively to Alembic. Isolated unit tests
that deliberately construct small in-memory receipt tables may install the
canonical SQLite approval guard explicitly through this helper.
"""

from __future__ import annotations

from sqlalchemy import text


APPROVAL_GUARD_TRIGGER = "trg_receipt_tables_preserve_explicit_approval"


def create_receipt_approval_guard_trigger(conn) -> None:
    """Install the canonical SQLite approval guard in an isolated test database."""
    conn.execute(
        text(
            f"""
            CREATE TRIGGER {APPROVAL_GUARD_TRIGGER}
            AFTER UPDATE OF parse_status, approved_at ON receipt_tables
            WHEN NEW.approved_at IS NOT NULL
             AND NEW.deleted_at IS NULL
             AND (
                    lower(trim(COALESCE(NEW.parse_status, ''))) NOT IN (
                        'approved', 'approved_override'
                    )
                    OR lower(trim(COALESCE(NEW.workflow_state, 'active'))) = 'returned_to_kassa'
             )
             AND lower(trim(COALESCE(NEW.workflow_state, 'active'))) NOT IN (
                    'archived', 'removed_reimport_allowed', 'legacy_deleted'
             )
             AND EXISTS (
                    SELECT 1
                    FROM raw_receipts rr
                    WHERE rr.id = NEW.raw_receipt_id
                      AND rr.deleted_at IS NULL
             )
            BEGIN
                UPDATE receipt_tables
                SET parse_status = CASE
                        WHEN COALESCE(NEW.totals_overridden, 0) <> 0
                        THEN 'approved_override'
                        ELSE 'approved'
                    END,
                    workflow_state = CASE
                        WHEN lower(trim(COALESCE(NEW.workflow_state, 'active'))) = 'returned_to_kassa'
                        THEN 'active'
                        ELSE NEW.workflow_state
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END
            """
        )
    )
