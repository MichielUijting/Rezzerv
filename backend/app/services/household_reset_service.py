from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


# These tables form the identity/access shell that must survive a household reset.
# auth_audit_log is deliberately retained as the immutable trace of destructive
# platform actions. Other household-scoped tables are reset.
PRESERVED_TABLES = frozenset({
    "household_registry",
    "household_memberships",
    "auth_membership_roles",
    "auth_audit_log",
    "app_users",
    "server_sessions",
})

FORBIDDEN_HOUSEHOLD_IDS = frozenset({"", "0"})


class HouseholdResetNotFoundError(LookupError):
    pass


class HouseholdResetConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ForeignKeyEdge:
    parent_table: str
    local_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]


# Legacy parts of the application predate full database-FK enforcement. Keep
# these proven ownership edges explicit so a full reset cannot leave dependent
# household data behind merely because PostgreSQL has no formal constraint.
MANUAL_FK_EDGES: dict[str, tuple[ForeignKeyEdge, ...]] = {
    "sublocations": (
        ForeignKeyEdge("spaces", ("space_id",), ("id",)),
    ),
    "receipt_table_lines": (
        ForeignKeyEdge("receipt_tables", ("receipt_table_id",), ("id",)),
    ),
    "receipt_inbound_events": (
        ForeignKeyEdge("receipt_tables", ("receipt_table_id",), ("id",)),
        ForeignKeyEdge("raw_receipts", ("raw_receipt_id",), ("id",)),
    ),
    "receipt_email_messages": (
        ForeignKeyEdge("raw_receipts", ("raw_receipt_id",), ("id",)),
    ),
    "purchase_import_lines": (
        ForeignKeyEdge("purchase_import_batches", ("batch_id",), ("id",)),
    ),
    "external_product_candidates": (
        ForeignKeyEdge("purchase_import_lines", ("purchase_import_line_id",), ("id",)),
    ),
    "household_article_settings": (
        ForeignKeyEdge("household_articles", ("household_article_id",), ("id",)),
    ),
    "household_article_notes": (
        ForeignKeyEdge("household_articles", ("household_article_id",), ("id",)),
    ),
    "support_messages": (
        ForeignKeyEdge("support_threads", ("thread_id",), ("id",)),
    ),
}


def _quote(conn: Connection, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(str(identifier))


def _table_columns(inspector, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns(table_name)
    }


def _registry_identity(conn: Connection, household_id: str) -> dict[str, Any]:
    inspector = inspect(conn)
    if not inspector.has_table("household_registry"):
        raise HouseholdResetConflictError("Huishoudregister ontbreekt; reset is afgebroken.")

    columns = _table_columns(inspector, "household_registry")
    id_column = "id" if "id" in columns else "household_id" if "household_id" in columns else None
    if not id_column:
        raise HouseholdResetConflictError("Huishoudregister heeft geen geldige identificatiekolom.")

    selected = [f"CAST({_quote(conn, id_column)} AS TEXT) AS household_id"]
    if "context_type" in columns:
        selected.append("context_type")
    if "naam" in columns:
        selected.append("naam AS household_name")
    elif "name" in columns:
        selected.append("name AS household_name")
    elif "household_name" in columns:
        selected.append("household_name")
    else:
        selected.append(f"CAST({_quote(conn, id_column)} AS TEXT) AS household_name")

    row = conn.execute(
        text(
            f"SELECT {', '.join(selected)} "
            f"FROM household_registry "
            f"WHERE CAST({_quote(conn, id_column)} AS TEXT)=:household_id "
            "LIMIT 1"
        ),
        {"household_id": household_id},
    ).mappings().first()
    if row is None:
        raise HouseholdResetNotFoundError("Huishouden niet gevonden.")

    context_type = str(row.get("context_type") or "regular").strip().lower()
    if household_id == "0" or context_type == "system":
        raise HouseholdResetConflictError(
            "Systeemhuishouden 0 kan niet met de huishoudreset worden gewist."
        )
    return dict(row)


def _membership_snapshot(conn: Connection, household_id: str) -> tuple[int, tuple[str, ...]]:
    inspector = inspect(conn)
    if not inspector.has_table("household_memberships"):
        raise HouseholdResetConflictError("Huishoudlidmaatschappen ontbreken; reset is afgebroken.")
    columns = _table_columns(inspector, "household_memberships")
    if "household_id" not in columns:
        raise HouseholdResetConflictError(
            "Huishoudlidmaatschappen missen household_id; reset is afgebroken."
        )

    user_expression = (
        "CAST(user_id AS TEXT)"
        if "user_id" in columns
        else "CAST(user_email AS TEXT)"
        if "user_email" in columns
        else "CAST(email AS TEXT)"
        if "email" in columns
        else "NULL"
    )
    rows = conn.execute(
        text(
            f"SELECT {user_expression} AS user_identity "
            "FROM household_memberships "
            "WHERE CAST(household_id AS TEXT)=:household_id "
            "ORDER BY 1 NULLS LAST"
        ),
        {"household_id": household_id},
    ).mappings().all()
    identities = tuple(
        str(row.get("user_identity") or "").strip()
        for row in rows
        if str(row.get("user_identity") or "").strip()
    )
    return len(rows), identities


def _foreign_keys(
    inspector,
    table_name: str,
    columns: dict[str, set[str]],
) -> tuple[ForeignKeyEdge, ...]:
    edges: list[ForeignKeyEdge] = []
    for fk in inspector.get_foreign_keys(table_name):
        parent = str(fk.get("referred_table") or "").strip()
        local = tuple(str(value) for value in (fk.get("constrained_columns") or ()) if value)
        remote = tuple(str(value) for value in (fk.get("referred_columns") or ()) if value)
        if not parent or not local or len(local) != len(remote):
            continue
        edges.append(ForeignKeyEdge(parent, local, remote))

    for edge in MANUAL_FK_EDGES.get(table_name, ()):
        if edge.parent_table not in columns:
            continue
        if not set(edge.local_columns).issubset(columns.get(table_name, set())):
            continue
        if not set(edge.parent_columns).issubset(columns.get(edge.parent_table, set())):
            continue
        if edge not in edges:
            edges.append(edge)

    return tuple(edges)


def _discover_reset_tables(conn: Connection) -> tuple[set[str], dict[str, tuple[ForeignKeyEdge, ...]], dict[str, set[str]]]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    columns = {table: _table_columns(inspector, table) for table in tables}
    fks = {
        table: _foreign_keys(inspector, table, columns)
        for table in tables
    }

    reset_tables = {
        table
        for table in tables
        if table not in PRESERVED_TABLES and "household_id" in columns[table]
    }

    # Include children that do not carry household_id themselves but belong to a
    # household-scoped parent (receipt lines, support messages, etc.).
    changed = True
    while changed:
        changed = False
        for child in sorted(tables - PRESERVED_TABLES - reset_tables):
            if any(edge.parent_table in reset_tables for edge in fks[child]):
                reset_tables.add(child)
                changed = True

    return reset_tables, fks, columns


def _child_first_order(
    reset_tables: set[str],
    fks: dict[str, tuple[ForeignKeyEdge, ...]],
) -> list[str]:
    # Edge child -> parent means the child must be deleted first.
    outgoing: dict[str, set[str]] = {
        table: {
            edge.parent_table
            for edge in fks[table]
            if edge.parent_table in reset_tables and edge.parent_table != table
        }
        for table in reset_tables
    }
    incoming_count = {table: 0 for table in reset_tables}
    for parents in outgoing.values():
        for parent in parents:
            incoming_count[parent] += 1

    ready = sorted(table for table, count in incoming_count.items() if count == 0)
    order: list[str] = []
    while ready:
        table = ready.pop(0)
        order.append(table)
        for parent in sorted(outgoing[table]):
            incoming_count[parent] -= 1
            if incoming_count[parent] == 0:
                ready.append(parent)
                ready.sort()

    if len(order) != len(reset_tables):
        cycle = sorted(table for table, count in incoming_count.items() if count > 0)
        raise HouseholdResetConflictError(
            "Huishoudreset is fail-closed gestopt door een cyclische database-relatie: "
            + ", ".join(cycle)
        )
    return order


def _target_predicate(
    conn: Connection,
    *,
    table_name: str,
    alias: str,
    reset_tables: set[str],
    fks: dict[str, tuple[ForeignKeyEdge, ...]],
    columns: dict[str, set[str]],
    stack: tuple[str, ...] = (),
) -> str:
    if table_name in stack:
        raise HouseholdResetConflictError(
            f"Cyclische resetpredicate gedetecteerd bij {table_name}."
        )

    clauses: list[str] = []
    if "household_id" in columns[table_name]:
        clauses.append(
            f"CAST({alias}.{_quote(conn, 'household_id')} AS TEXT)=:household_id"
        )

    next_stack = (*stack, table_name)
    for index, edge in enumerate(fks[table_name]):
        if edge.parent_table not in reset_tables or edge.parent_table == table_name:
            continue
        parent_alias = f"p{len(stack)}_{index}"
        parent_predicate = _target_predicate(
            conn,
            table_name=edge.parent_table,
            alias=parent_alias,
            reset_tables=reset_tables,
            fks=fks,
            columns=columns,
            stack=next_stack,
        )
        if not parent_predicate:
            continue
        joins = " AND ".join(
            f"{parent_alias}.{_quote(conn, parent_col)} = "
            f"{alias}.{_quote(conn, local_col)}"
            for local_col, parent_col in zip(
                edge.local_columns,
                edge.parent_columns,
            )
        )
        clauses.append(
            f"EXISTS (SELECT 1 FROM {_quote(conn, edge.parent_table)} {parent_alias} "
            f"WHERE {joins} AND ({parent_predicate}))"
        )

    return " OR ".join(f"({clause})" for clause in clauses)


def _revoke_household_sessions(conn: Connection, household_id: str) -> int:
    inspector = inspect(conn)
    if not inspector.has_table("server_sessions"):
        return 0
    columns = _table_columns(inspector, "server_sessions")
    required = {"active_household_id", "revoked_at"}
    if not required.issubset(columns):
        raise HouseholdResetConflictError(
            "Sessietabel wijkt af; reset is afgebroken om stale toegang te voorkomen."
        )

    now = datetime.now(timezone.utc)
    updated_at_sql = ", updated_at=:now" if "updated_at" in columns else ""
    result = conn.execute(
        text(
            "UPDATE server_sessions "
            f"SET revoked_at=:now{updated_at_sql} "
            "WHERE CAST(active_household_id AS TEXT)=:household_id "
            "AND revoked_at IS NULL"
        ),
        {"now": now, "household_id": household_id},
    )
    return int(result.rowcount or 0)


def reset_household_data(
    conn: Connection,
    household_id: str,
    *,
    confirmation: str,
) -> dict[str, Any]:
    target = str(household_id or "").strip()
    if target in FORBIDDEN_HOUSEHOLD_IDS:
        raise HouseholdResetConflictError(
            "Geef een regulier huishouden op; huishouden 0 is uitgesloten."
        )

    expected_confirmation = f"RESET {target}"
    if str(confirmation or "").strip() != expected_confirmation:
        raise HouseholdResetConflictError(
            f"Bevestiging klopt niet. Typ exact: {expected_confirmation}"
        )

    household = _registry_identity(conn, target)
    member_count_before, member_identities_before = _membership_snapshot(conn, target)
    reset_tables, fks, columns = _discover_reset_tables(conn)
    order = _child_first_order(reset_tables, fks)

    deleted_by_table: dict[str, int] = {}
    for table_name in order:
        predicate = _target_predicate(
            conn,
            table_name=table_name,
            alias="target",
            reset_tables=reset_tables,
            fks=fks,
            columns=columns,
        )
        if not predicate:
            continue
        result = conn.execute(
            text(
                f"DELETE FROM {_quote(conn, table_name)} AS target "
                f"WHERE {predicate}"
            ),
            {"household_id": target},
        )
        if int(result.rowcount or 0):
            deleted_by_table[table_name] = int(result.rowcount or 0)

    # Fail closed: no household-scoped operational data may survive.
    residual: dict[str, int] = {}
    for table_name in order:
        predicate = _target_predicate(
            conn,
            table_name=table_name,
            alias="target",
            reset_tables=reset_tables,
            fks=fks,
            columns=columns,
        )
        if not predicate:
            continue
        count = int(
            conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {_quote(conn, table_name)} AS target "
                    f"WHERE {predicate}"
                ),
                {"household_id": target},
            ).scalar()
            or 0
        )
        if count:
            residual[table_name] = count
    if residual:
        raise HouseholdResetConflictError(
            "Resetcontrole vond resterende huishouddata; volledige transactie is afgebroken: "
            + ", ".join(f"{table}={count}" for table, count in sorted(residual.items()))
        )

    member_count_after, member_identities_after = _membership_snapshot(conn, target)
    if (
        member_count_after != member_count_before
        or member_identities_after != member_identities_before
    ):
        raise HouseholdResetConflictError(
            "Lidmaatschappen veranderden onverwacht; volledige resettransactie is afgebroken."
        )

    sessions_revoked = _revoke_household_sessions(conn, target)
    return {
        "status": "reset",
        "household_id": target,
        "household_name": str(household.get("household_name") or target),
        "preserved_member_count": member_count_after,
        "sessions_revoked": sessions_revoked,
        "deleted_row_count": sum(deleted_by_table.values()),
        "deleted_by_table": dict(sorted(deleted_by_table.items())),
        "preserved": [
            "household_registry",
            "household_memberships",
            "auth_membership_roles",
            "app_users",
            "auth_audit_log",
        ],
    }
