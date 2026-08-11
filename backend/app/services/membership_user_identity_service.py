from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def _columns(conn: Connection, table: str) -> set[str]:
    inspector = inspect(conn)
    if table not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table)}


def backfill_membership_user_ids(conn: Connection) -> int:
    """Align legacy household membership user ids with canonical app_users ids.

    Rezzerv's server session identifies an actor by ``app_users.id``. Older
    memberships can still be linked primarily by ``user_email`` and may have an
    empty or stale ``user_id``. The Superuser selector must use the same
    canonical identity as actor attribution, otherwise a valid actor can never
    match the selected household member.

    The backfill is deterministic: it only updates a membership when its email
    matches exactly one app user case-insensitively. No heuristic identity
    inference is performed.
    """
    membership_columns = _columns(conn, "household_memberships")
    user_columns = _columns(conn, "app_users")
    if not {"user_id", "user_email"}.issubset(membership_columns):
        return 0
    if not {"id", "email"}.issubset(user_columns):
        return 0

    candidates = conn.execute(text("""
        SELECT
            hm.rowid AS membership_rowid,
            CAST(hm.user_id AS TEXT) AS current_user_id,
            u.id AS canonical_user_id
        FROM household_memberships hm
        JOIN app_users u
          ON lower(trim(u.email)) = lower(trim(hm.user_email))
        WHERE trim(COALESCE(hm.user_email, '')) <> ''
          AND (
                hm.user_id IS NULL
             OR trim(CAST(hm.user_id AS TEXT)) = ''
             OR CAST(hm.user_id AS TEXT) <> CAST(u.id AS TEXT)
          )
          AND 1 = (
              SELECT COUNT(*)
              FROM app_users ux
              WHERE lower(trim(ux.email)) = lower(trim(hm.user_email))
          )
    """)).mappings().all()

    updated = 0
    for row in candidates:
        result = conn.execute(
            text("UPDATE household_memberships SET user_id = :user_id WHERE rowid = :rowid"),
            {
                "user_id": str(row["canonical_user_id"]),
                "rowid": row["membership_rowid"],
            },
        )
        updated += max(int(result.rowcount or 0), 0)
    return updated
