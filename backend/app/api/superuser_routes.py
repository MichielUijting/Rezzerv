"""Read-only Superuser beheercentrum foundation, overview and usage routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    write_authorization_audit,
)
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session
from app.services.support_message_service import ensure_support_message_foundation


SUPERUSER_ROLE_KEY = "platform.superuser"
SUPERUSER_TABS = ("Overzicht", "Huishoudens", "Gebruik", "Kassabonnen", "Systeem")
TREND_DAYS = 7


def _require_platform_superuser(conn, raw_session_id: str | None):
    context = resolve_server_session(conn, raw_session_id)
    ensure_authorization_foundation(conn)
    granted = conn.execute(
        text(
            """
            SELECT 1
            FROM auth_platform_user_roles
            WHERE user_id = :user_id
              AND role_key = :role_key
              AND active = TRUE
            LIMIT 1
            """
        ),
        {"user_id": context.user_id, "role_key": SUPERUSER_ROLE_KEY},
    ).first()
    if not granted:
        raise HTTPException(
            status_code=403,
            detail="Alleen de platform-supergebruiker heeft toegang tot het Rezzerv Beheercentrum",
        )
    return context


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _first(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _active_clauses(columns: set[str], *, alias: str = "") -> list[str]:
    prefix = f"{alias}." if alias else ""
    clauses: list[str] = []
    if "deleted_at" in columns:
        clauses.append(f"{prefix}deleted_at IS NULL")
    if "is_deleted" in columns:
        clauses.append(f"COALESCE({prefix}is_deleted, 0) = 0")
    return clauses


def _calendar_days() -> list[str]:
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=offset)).isoformat() for offset in range(TREND_DAYS - 1, -1, -1)]


def _historical_count_series(
    conn,
    table_name: str,
    *,
    current_value: int,
    created_candidates: tuple[str, ...] = ("created_at",),
    distinct_column: str | None = None,
    extra_clauses: tuple[str, ...] = (),
) -> list[dict]:
    """Reconstruct seven end-of-calendar-day counts from existing timestamps only."""
    days = _calendar_days()
    columns = _columns(conn, table_name)
    created_column = _first(columns, *created_candidates)
    if not created_column:
        return []

    deleted_column = _first(columns, "deleted_at", "archived_at")
    result: list[dict] = []
    for index, day in enumerate(days):
        if index == len(days) - 1:
            value = int(current_value)
        else:
            end = f"{day}T23:59:59.999999+00:00"
            clauses = [f"{created_column} <= CAST(:end AS TIMESTAMPTZ)", *extra_clauses]
            if deleted_column:
                clauses.append(f"({deleted_column} IS NULL OR {deleted_column} > CAST(:end AS TIMESTAMPTZ))")
            elif "is_deleted" in columns:
                clauses.append("COALESCE(is_deleted, FALSE) = FALSE")
            expression = f"DISTINCT CAST({distinct_column} AS TEXT)" if distinct_column else "*"
            value = int(conn.execute(
                text(f"SELECT COUNT({expression}) FROM {table_name} WHERE {' AND '.join(clauses)}"),
                {"end": end},
            ).scalar() or 0)
        result.append({"date": day, "value": value})
    return result


def _open_notification_series(conn, current_value: int) -> list[dict]:
    days = _calendar_days()
    columns = _columns(conn, "support_threads")
    if "created_at" not in columns:
        return []
    result: list[dict] = []
    for index, day in enumerate(days):
        if index == len(days) - 1:
            value = int(current_value)
        else:
            end = f"{day}T23:59:59.999999+00:00"
            value = int(conn.execute(text("""
                SELECT COUNT(*)
                FROM support_threads
                WHERE created_at <= CAST(:end AS TIMESTAMPTZ)
                  AND (closed_at IS NULL OR closed_at > CAST(:end AS TIMESTAMPTZ))
            """), {"end": end}).scalar() or 0)
        result.append({"date": day, "value": value})
    return result


def _count_for_household(conn, table_name: str, household_id: str, *, household_column: str = "household_id") -> int:
    columns = _columns(conn, table_name)
    if household_column not in columns:
        return 0
    clauses = [f"CAST({household_column} AS TEXT)=:household_id", *_active_clauses(columns)]
    return int(conn.execute(
        text(f"SELECT COUNT(*) FROM {table_name} WHERE {' AND '.join(clauses)}"),
        {"household_id": household_id},
    ).scalar() or 0)


def _latest_for_household(conn, table_name: str, household_id: str, candidates: tuple[str, ...], *, household_column: str = "household_id"):
    columns = _columns(conn, table_name)
    if household_column not in columns:
        return None
    date_column = _first(columns, *candidates)
    if not date_column:
        return None
    clauses = [f"CAST({household_column} AS TEXT)=:household_id", *_active_clauses(columns)]
    return conn.execute(
        text(f"SELECT MAX({date_column}) FROM {table_name} WHERE {' AND '.join(clauses)}"),
        {"household_id": household_id},
    ).scalar()


def _platform_overview(conn) -> dict:
    registry_columns = _columns(conn, "household_registry")
    household_id_column = _first(registry_columns, "id", "household_id")
    household_name_column = _first(registry_columns, "naam", "name", "household_name")
    household_status_column = _first(registry_columns, "status")

    active_households = 0
    household_status_clauses: list[str] = []
    if household_id_column:
        clauses = [*_active_clauses(registry_columns)]
        if household_status_column:
            household_status_clauses.append(f"lower(trim(COALESCE({household_status_column}, 'active'))) = 'active'")
            clauses.extend(household_status_clauses)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        active_households = int(conn.execute(text(f"SELECT COUNT(*) FROM household_registry{where}")).scalar() or 0)

    membership_columns = _columns(conn, "household_memberships")
    user_column = _first(membership_columns, "user_id", "user_email", "email")
    active_users = 0
    membership_status_clauses: list[str] = []
    if user_column:
        clauses = [*_active_clauses(membership_columns)]
        if "status" in membership_columns:
            membership_status_clauses.append("lower(trim(COALESCE(status, 'active'))) = 'active'")
            clauses.extend(membership_status_clauses)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        active_users = int(conn.execute(text(
            f"SELECT COUNT(DISTINCT CAST({user_column} AS TEXT)) FROM household_memberships{where}"
        )).scalar() or 0)

    receipt_columns = _columns(conn, "receipt_tables")
    receipt_count = 0
    last_receipt_at = None
    if "household_id" in receipt_columns:
        clauses = [*_active_clauses(receipt_columns)]
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        receipt_count = int(conn.execute(text(f"SELECT COUNT(*) FROM receipt_tables{where}")).scalar() or 0)
        date_column = _first(receipt_columns, "purchase_at", "imported_at", "created_at")
        if date_column:
            last_receipt_at = conn.execute(text(f"SELECT MAX({date_column}) FROM receipt_tables{where}")).scalar()

    ensure_support_message_foundation(conn)
    open_notifications = int(conn.execute(text(
        "SELECT COUNT(*) FROM support_threads WHERE status IN ('Open', 'In behandeling')"
    )).scalar() or 0)

    trends = {
        "active_households": _historical_count_series(
            conn,
            "household_registry",
            current_value=active_households,
            created_candidates=("created_at", "registered_at"),
            extra_clauses=tuple(household_status_clauses),
        ),
        "active_users": _historical_count_series(
            conn,
            "household_memberships",
            current_value=active_users,
            created_candidates=("created_at", "joined_at", "added_at"),
            distinct_column=user_column,
            extra_clauses=tuple(membership_status_clauses),
        ) if user_column else [],
        "receipt_count": _historical_count_series(
            conn,
            "receipt_tables",
            current_value=receipt_count,
            created_candidates=("imported_at", "created_at", "purchase_at"),
        ),
        "open_notifications": _open_notification_series(conn, open_notifications),
    }

    attention: dict[str, dict] = {}

    inventory_columns = _columns(conn, "inventory")
    if "household_id" in inventory_columns and "aantal" in inventory_columns:
        clauses = ["COALESCE(aantal, 0) < 0", *_active_clauses(inventory_columns)]
        rows = conn.execute(text(f"""
            SELECT CAST(household_id AS TEXT) AS household_id, COUNT(*) AS issue_count
            FROM inventory
            WHERE {' AND '.join(clauses)}
            GROUP BY CAST(household_id AS TEXT)
        """)).mappings().all()
        for row in rows:
            household_id = str(row["household_id"])
            item = attention.setdefault(household_id, {"household_id": household_id, "signals": [], "signal_count": 0})
            count = int(row["issue_count"] or 0)
            item["signals"].append(f"{count} negatieve voorraadregel(s)")
            item["signal_count"] += count

    notification_rows = conn.execute(text("""
        SELECT CAST(household_id AS TEXT) AS household_id, COUNT(*) AS issue_count
        FROM support_threads
        WHERE household_id IS NOT NULL AND status IN ('Open', 'In behandeling')
        GROUP BY CAST(household_id AS TEXT)
    """)).mappings().all()
    for row in notification_rows:
        household_id = str(row["household_id"])
        item = attention.setdefault(household_id, {"household_id": household_id, "signals": [], "signal_count": 0})
        count = int(row["issue_count"] or 0)
        item["signals"].append(f"{count} open melding(en)")
        item["signal_count"] += count

    if household_id_column and attention:
        ids = list(attention)
        placeholders = ", ".join(f":hid_{index}" for index in range(len(ids)))
        params = {f"hid_{index}": household_id for index, household_id in enumerate(ids)}
        name_sql = household_name_column or household_id_column
        rows = conn.execute(text(f"""
            SELECT CAST({household_id_column} AS TEXT) AS household_id, {name_sql} AS household_name
            FROM household_registry
            WHERE CAST({household_id_column} AS TEXT) IN ({placeholders})
        """), params).mappings().all()
        for row in rows:
            household_id = str(row["household_id"])
            if household_id in attention:
                attention[household_id]["household_name"] = str(row["household_name"] or household_id)

    attention_items = []
    for item in attention.values():
        item["household_name"] = item.get("household_name") or item["household_id"]
        item["signal"] = " · ".join(item.pop("signals"))
        attention_items.append(item)
    attention_items.sort(key=lambda item: (-int(item["signal_count"]), str(item["household_name"]).lower()))

    return {
        "access": "read_only",
        "metrics": {
            "active_households": active_households,
            "active_users": active_users,
            "receipt_count": receipt_count,
            "open_notifications": open_notifications,
            "last_receipt_at": last_receipt_at,
        },
        "trends": trends,
        "trend_period": {"calendar_days": TREND_DAYS, "timezone": "UTC"},
        "attention_items": attention_items,
        "notification_route": "/superuser/meldingen",
    }


def _platform_usage(conn) -> dict:
    """Project existing operational data into a read-only usage overview; no new tracking is introduced."""
    registry_columns = _columns(conn, "household_registry")
    household_id_column = _first(registry_columns, "id", "household_id")
    household_name_column = _first(registry_columns, "naam", "name", "household_name")
    household_status_column = _first(registry_columns, "status")
    if not household_id_column:
        return {"access": "read_only", "tracking": "existing_data_only", "metrics": {}, "items": []}

    clauses = [*_active_clauses(registry_columns)]
    if household_status_column:
        clauses.append(f"lower(trim(COALESCE({household_status_column}, 'active'))) = 'active'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    name_sql = household_name_column or household_id_column
    households = conn.execute(text(f"""
        SELECT CAST({household_id_column} AS TEXT) AS household_id, {name_sql} AS household_name
        FROM household_registry{where}
        ORDER BY lower(CAST({name_sql} AS TEXT)), CAST({household_id_column} AS TEXT)
    """)).mappings().all()

    membership_columns = _columns(conn, "household_memberships")
    items = []
    total_receipts = 0
    total_inventory_events = 0
    total_support_threads = 0
    households_with_session_activity = 0

    ensure_support_message_foundation(conn)
    for row in households:
        household_id = str(row["household_id"])
        member_count = 0
        if "household_id" in membership_columns:
            membership_clauses = ["CAST(household_id AS TEXT)=:household_id", *_active_clauses(membership_columns)]
            if "status" in membership_columns:
                membership_clauses.append("lower(trim(COALESCE(status, 'active'))) = 'active'")
            member_count = int(conn.execute(text(
                f"SELECT COUNT(*) FROM household_memberships WHERE {' AND '.join(membership_clauses)}"
            ), {"household_id": household_id}).scalar() or 0)

        receipt_count = _count_for_household(conn, "receipt_tables", household_id)
        inventory_event_count = _count_for_household(conn, "inventory_events", household_id)
        support_thread_count = int(conn.execute(text("""
            SELECT COUNT(*) FROM support_threads WHERE CAST(household_id AS TEXT)=:household_id
        """), {"household_id": household_id}).scalar() or 0)
        last_active_at = _latest_for_household(
            conn,
            "server_sessions",
            household_id,
            ("updated_at", "issued_at", "created_at"),
            household_column="active_household_id",
        )
        if last_active_at is not None:
            households_with_session_activity += 1

        total_receipts += receipt_count
        total_inventory_events += inventory_event_count
        total_support_threads += support_thread_count
        items.append({
            "household_id": household_id,
            "household_name": str(row["household_name"] or household_id),
            "active_member_count": member_count,
            "receipt_count": receipt_count,
            "inventory_event_count": inventory_event_count,
            "support_thread_count": support_thread_count,
            "last_active_at": last_active_at,
        })

    return {
        "access": "read_only",
        "tracking": "existing_data_only",
        "metrics": {
            "active_households": len(items),
            "households_with_session_activity": households_with_session_activity,
            "receipt_count": total_receipts,
            "inventory_event_count": total_inventory_events,
            "support_thread_count": total_support_threads,
        },
        "items": items,
    }


def create_superuser_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/api/superuser/bootstrap")
    def bootstrap(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
        return {
            "access": "read_only",
            "role": SUPERUSER_ROLE_KEY,
            "tabs": list(SUPERUSER_TABS),
            "user_id": context.user_id,
        }

    @router.get("/api/superuser/overview")
    def overview(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
            payload = _platform_overview(conn)
            write_authorization_audit(
                conn,
                actor_user_id=context.user_id,
                actor_type="platform_superuser",
                action="superuser.overview.viewed",
                object_type="superuser_overview",
                new_value={"attention_count": len(payload["attention_items"])},
                reason="Superuser bekeek platformoverzicht",
            )
        return payload

    @router.get("/api/superuser/usage")
    def usage(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
            payload = _platform_usage(conn)
            write_authorization_audit(
                conn,
                actor_user_id=context.user_id,
                actor_type="platform_superuser",
                action="superuser.usage.viewed",
                object_type="superuser_usage",
                new_value={"household_count": len(payload["items"]), "tracking": payload["tracking"]},
                reason="Superuser bekeek bestaand platformgebruik",
            )
        return payload

    @router.post("/api/superuser/audit/open", status_code=204)
    def audit_open(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
            write_authorization_audit(
                conn,
                actor_user_id=context.user_id,
                actor_type="platform_superuser",
                action="superuser.manage_center.opened",
                object_type="superuser_manage_center",
                reason="Superuser opende Rezzerv Beheercentrum",
            )
        return None

    return router
