from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_membership_service import (
    create_canonical_membership_role,
    resolve_effective_household_role,
)
from app.services.household_onboarding_service import start_new_household_onboarding
from app.services.server_session_service import (
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
)


DEFAULT_ADDITIONAL_HOUSEHOLD_NAME = "Nieuw huishouden"
SYSTEM_HOUSEHOLD_ID = "0"

PRESERVED_TABLES = frozenset({
    "app_users",
    "auth_audit_log",
    "auth_platform_user_roles",
    "server_sessions",
    "household_registry",
})

@dataclass(frozen=True)
class OwnershipEdge:
    parent_table: str
    local_columns: tuple[str, ...]
    parent_columns: tuple[str, ...]


# Legacy parts of Inhuis contain logical ownership relations that are not all
# represented as PostgreSQL foreign keys. These edges keep deletion complete.
MANUAL_OWNERSHIP_EDGES: dict[str, tuple[OwnershipEdge, ...]] = {
    "sublocations": (
        OwnershipEdge("spaces", ("space_id",), ("id",)),
    ),
    "receipt_table_lines": (
        OwnershipEdge("receipt_tables", ("receipt_table_id",), ("id",)),
    ),
    "receipt_inbound_events": (
        OwnershipEdge("receipt_tables", ("receipt_table_id",), ("id",)),
        OwnershipEdge("raw_receipts", ("raw_receipt_id",), ("id",)),
    ),
    "receipt_email_messages": (
        OwnershipEdge("raw_receipts", ("raw_receipt_id",), ("id",)),
    ),
    "purchase_import_lines": (
        OwnershipEdge("purchase_import_batches", ("batch_id",), ("id",)),
    ),
    "external_product_candidates": (
        OwnershipEdge("purchase_import_lines", ("purchase_import_line_id",), ("id",)),
    ),
    "household_article_settings": (
        OwnershipEdge("household_articles", ("household_article_id",), ("id",)),
    ),
    "household_article_notes": (
        OwnershipEdge("household_articles", ("household_article_id",), ("id",)),
    ),
    "support_messages": (
        OwnershipEdge("support_threads", ("thread_id",), ("id",)),
    ),
    "auth_membership_roles": (
        OwnershipEdge("household_memberships", ("membership_id",), ("id",)),
    ),
    "auth_membership_permission_overrides": (
        OwnershipEdge("household_memberships", ("membership_id",), ("id",)),
    ),
}


class HouseholdLifecycleConflictError(RuntimeError):
    pass


class HouseholdLifecycleNotFoundError(LookupError):
    pass


def _columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {
        str(column.get("name") or "").strip()
        for column in inspector.get_columns(table_name)
    }


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def _quote(conn: Connection, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(str(identifier))


def _normalize_household_name(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise ValueError("Naam huishouden is verplicht")
    if len(normalized) > 120:
        raise ValueError("Naam huishouden mag maximaal 120 tekens bevatten")
    return normalized


def create_additional_household(
    conn: Connection,
    *,
    user_id: str,
    email: str,
    household_name: str = DEFAULT_ADDITIONAL_HOUSEHOLD_NAME,
) -> dict[str, str]:
    normalized_user_id = str(user_id or "").strip()
    normalized_email = str(email or "").strip().lower()
    normalized_name = _normalize_household_name(household_name)
    if not normalized_user_id or not normalized_email:
        raise ValueError("Geldige gebruikersidentiteit ontbreekt")

    account = conn.execute(
        text(
            "SELECT id, email FROM app_users "
            "WHERE id=:user_id AND lower(trim(email))=:email LIMIT 1"
        ),
        {"user_id": normalized_user_id, "email": normalized_email},
    ).mappings().first()
    if not account:
        raise HouseholdLifecycleConflictError("Account kon niet eenduidig worden vastgesteld.")

    household_columns = _columns(conn, "household_registry")
    membership_columns = _columns(conn, "household_memberships")
    household_id_column = _pick(household_columns, "id", "household_id")
    household_name_column = _pick(household_columns, "naam", "name")
    membership_id_column = _pick(membership_columns, "id", "membership_id")
    membership_household_column = _pick(membership_columns, "household_id")
    membership_role_column = _pick(membership_columns, "role", "rol")
    membership_email_column = _pick(membership_columns, "user_email", "email")
    membership_user_column = _pick(membership_columns, "user_id")

    if not household_id_column or not household_name_column:
        raise HouseholdLifecycleConflictError("Huishoudregister wijkt af; aanmaken is afgebroken.")
    if (
        not membership_id_column
        or not membership_household_column
        or not membership_role_column
        or (not membership_email_column and not membership_user_column)
    ):
        raise HouseholdLifecycleConflictError("Lidmaatschapsschema wijkt af; aanmaken is afgebroken.")

    household_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())

    registry_columns = [household_id_column, household_name_column]
    registry_values = [":household_id", ":household_name"]
    registry_params = {
        "household_id": household_id,
        "household_name": normalized_name,
    }
    if "context_type" in household_columns:
        registry_columns.append("context_type")
        registry_values.append("'regular'")
    if "created_at" in household_columns:
        registry_columns.append("created_at")
        registry_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in household_columns:
        registry_columns.append("updated_at")
        registry_values.append("CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"INSERT INTO household_registry ({', '.join(registry_columns)}) "
            f"VALUES ({', '.join(registry_values)})"
        ),
        registry_params,
    )

    membership_insert_columns = [
        membership_id_column,
        membership_household_column,
        membership_role_column,
    ]
    membership_insert_values = [":membership_id", ":household_id", "'admin'"]
    membership_params = {
        "membership_id": membership_id,
        "household_id": household_id,
        "email": normalized_email,
        "user_id": normalized_user_id,
    }
    if membership_email_column:
        membership_insert_columns.append(membership_email_column)
        membership_insert_values.append(":email")
    if membership_user_column:
        membership_insert_columns.append(membership_user_column)
        membership_insert_values.append(":user_id")
    if "status" in membership_columns:
        membership_insert_columns.append("status")
        membership_insert_values.append("'active'")
    if "active" in membership_columns:
        membership_insert_columns.append("active")
        membership_insert_values.append("1")
    if "created_at" in membership_columns:
        membership_insert_columns.append("created_at")
        membership_insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in membership_columns:
        membership_insert_columns.append("updated_at")
        membership_insert_values.append("CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"INSERT INTO household_memberships ({', '.join(membership_insert_columns)}) "
            f"VALUES ({', '.join(membership_insert_values)})"
        ),
        membership_params,
    )

    role_key = create_canonical_membership_role(
        conn,
        household_id=household_id,
        membership_id=membership_id,
        legacy_role="admin",
    )
    if role_key != "household.admin":
        raise HouseholdLifecycleConflictError("Nieuw huishouden kreeg geen Beheerderrol.")

    onboarding = start_new_household_onboarding(conn, household_id)
    if not onboarding.initial_choice_required:
        raise HouseholdLifecycleConflictError("Nieuw huishouden kreeg geen schone onboardingstatus.")

    return {
        "household_id": household_id,
        "household_name": normalized_name,
        "membership_id": membership_id,
        "role": "admin",
        "onboarding_status": onboarding.onboarding_status,
    }


def household_deletion_eligibility(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    active_household_id: str | None,
) -> dict[str, object]:
    target = str(household_id or "").strip()
    if not target or target == SYSTEM_HOUSEHOLD_ID:
        return {"can_delete": False, "reason": "system_or_missing"}
    if target == str(active_household_id or "").strip():
        return {"can_delete": False, "reason": "active_household"}

    registry_columns = _columns(conn, "household_registry")
    registry_id = _pick(registry_columns, "id", "household_id")
    registry_name = _pick(registry_columns, "naam", "name")
    if not registry_id or not registry_name:
        return {"can_delete": False, "reason": "schema_invalid"}

    household = conn.execute(
        text(
            f"SELECT {registry_name} AS household_name "
            f"FROM household_registry WHERE CAST({registry_id} AS TEXT)=:household_id LIMIT 1"
        ),
        {"household_id": target},
    ).mappings().first()
    if not household:
        return {"can_delete": False, "reason": "not_found"}

    membership_id_sql = membership_id_expression(conn, membership_alias="hm")
    active_condition = membership_active_condition(conn, membership_alias="hm")
    join_condition = membership_user_join_condition(conn, membership_alias="hm", user_alias="u")

    actor = conn.execute(
        text(
            f"""
            SELECT {membership_id_sql} AS membership_id, hm.role
            FROM household_memberships hm
            JOIN app_users u ON {join_condition}
            WHERE u.id=:user_id
              AND CAST(hm.household_id AS TEXT)=:household_id
              AND {active_condition}
            LIMIT 1
            """
        ),
        {"user_id": str(user_id), "household_id": target},
    ).mappings().first()
    if not actor:
        return {"can_delete": False, "reason": "not_member"}

    role_key = resolve_effective_household_role(
        conn,
        household_id=target,
        membership_id=str(actor.get("membership_id") or ""),
        legacy_role=actor.get("role"),
    )
    if role_key != "household.admin":
        return {"can_delete": False, "reason": "not_admin"}

    member_count = int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM household_memberships hm "
                f"WHERE CAST(hm.household_id AS TEXT)=:household_id AND {active_condition}"
            ),
            {"household_id": target},
        ).scalar()
        or 0
    )
    if member_count != 1:
        return {
            "can_delete": False,
            "reason": "other_members",
            "member_count": member_count,
        }

    return {
        "can_delete": True,
        "reason": "sole_admin",
        "member_count": 1,
        "household_name": str(household.get("household_name") or "").strip() or "Huishouden",
    }


def _ownership_edges(
    inspector,
    table_name: str,
    columns_by_table: dict[str, set[str]],
) -> tuple[OwnershipEdge, ...]:
    edges: list[OwnershipEdge] = []
    for fk in inspector.get_foreign_keys(table_name):
        parent = str(fk.get("referred_table") or "").strip()
        local = tuple(str(value) for value in (fk.get("constrained_columns") or ()) if value)
        remote = tuple(str(value) for value in (fk.get("referred_columns") or ()) if value)
        if parent and local and len(local) == len(remote):
            edges.append(OwnershipEdge(parent, local, remote))

    for edge in MANUAL_OWNERSHIP_EDGES.get(table_name, ()):
        if edge.parent_table not in columns_by_table:
            continue
        if not set(edge.local_columns).issubset(columns_by_table.get(table_name, set())):
            continue
        if not set(edge.parent_columns).issubset(columns_by_table.get(edge.parent_table, set())):
            continue
        if edge not in edges:
            edges.append(edge)
    return tuple(edges)


def _discover_household_tables(
    conn: Connection,
) -> tuple[set[str], dict[str, tuple[OwnershipEdge, ...]], dict[str, set[str]]]:
    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    columns = {table: _columns(conn, table) for table in tables}
    edges = {
        table: _ownership_edges(inspector, table, columns)
        for table in tables
    }

    targets = {
        table
        for table in tables
        if table not in PRESERVED_TABLES and "household_id" in columns[table]
    }
    changed = True
    while changed:
        changed = False
        for child in sorted(tables - PRESERVED_TABLES - targets):
            if any(edge.parent_table in targets for edge in edges[child]):
                targets.add(child)
                changed = True
    return targets, edges, columns


def _child_first_order(
    tables: set[str],
    edges: dict[str, tuple[OwnershipEdge, ...]],
) -> list[str]:
    outgoing = {
        table: {
            edge.parent_table
            for edge in edges[table]
            if edge.parent_table in tables and edge.parent_table != table
        }
        for table in tables
    }
    incoming = {table: 0 for table in tables}
    for parents in outgoing.values():
        for parent in parents:
            incoming[parent] += 1

    ready = sorted(table for table, count in incoming.items() if count == 0)
    order: list[str] = []
    while ready:
        table = ready.pop(0)
        order.append(table)
        for parent in sorted(outgoing[table]):
            incoming[parent] -= 1
            if incoming[parent] == 0:
                ready.append(parent)
                ready.sort()

    if len(order) != len(tables):
        cycle = sorted(table for table, count in incoming.items() if count > 0)
        raise HouseholdLifecycleConflictError(
            "Huishouden verwijderen is fail-closed gestopt door cyclische datarelaties: "
            + ", ".join(cycle)
        )
    return order


def _target_predicate(
    conn: Connection,
    *,
    table_name: str,
    alias: str,
    target_tables: set[str],
    edges: dict[str, tuple[OwnershipEdge, ...]],
    columns: dict[str, set[str]],
    stack: tuple[str, ...] = (),
) -> str:
    if table_name in stack:
        raise HouseholdLifecycleConflictError(
            f"Cyclische verwijderpredicate gedetecteerd bij {table_name}."
        )

    clauses: list[str] = []
    if "household_id" in columns[table_name]:
        clauses.append(
            f"CAST({alias}.{_quote(conn, 'household_id')} AS TEXT)=:household_id"
        )

    next_stack = (*stack, table_name)
    for index, edge in enumerate(edges[table_name]):
        if edge.parent_table not in target_tables or edge.parent_table == table_name:
            continue
        parent_alias = f"p{len(stack)}_{index}"
        parent_predicate = _target_predicate(
            conn,
            table_name=edge.parent_table,
            alias=parent_alias,
            target_tables=target_tables,
            edges=edges,
            columns=columns,
            stack=next_stack,
        )
        if not parent_predicate:
            continue
        joins = " AND ".join(
            f"{parent_alias}.{_quote(conn, parent_col)}="
            f"{alias}.{_quote(conn, local_col)}"
            for local_col, parent_col in zip(edge.local_columns, edge.parent_columns)
        )
        clauses.append(
            f"EXISTS (SELECT 1 FROM {_quote(conn, edge.parent_table)} {parent_alias} "
            f"WHERE {joins} AND ({parent_predicate}))"
        )
    return " OR ".join(f"({clause})" for clause in clauses)


def delete_additional_household(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    active_household_id: str | None,
    confirmation: str,
) -> dict[str, object]:
    target = str(household_id or "").strip()
    eligibility = household_deletion_eligibility(
        conn,
        household_id=target,
        user_id=user_id,
        active_household_id=active_household_id,
    )
    if not eligibility.get("can_delete"):
        reason = str(eligibility.get("reason") or "not_allowed")
        messages = {
            "active_household": "Wissel eerst naar een ander huishouden voordat je dit huishouden verwijdert.",
            "other_members": "Dit huishouden kan pas worden verwijderd wanneer alleen jij als Beheerder overblijft.",
            "not_admin": "Alleen een Beheerder van dit huishouden kan het verwijderen.",
            "not_member": "Je bent geen actief lid van dit huishouden.",
            "system_or_missing": "Dit huishouden kan niet worden verwijderd.",
            "not_found": "Huishouden niet gevonden.",
        }
        raise HouseholdLifecycleConflictError(messages.get(reason, "Huishouden kan niet veilig worden verwijderd."))

    expected = f"VERWIJDER {target}"
    if str(confirmation or "").strip() != expected:
        raise HouseholdLifecycleConflictError(f"Bevestiging klopt niet. Typ exact: {expected}")

    target_tables, edges, columns = _discover_household_tables(conn)
    order = _child_first_order(target_tables, edges)
    deleted_by_table: dict[str, int] = {}

    # Revoke stale sessions pointing to the soon-to-be deleted household while
    # preserving account/session audit history.
    session_columns = _columns(conn, "server_sessions")
    if {"active_household_id", "revoked_at"}.issubset(session_columns):
        now = datetime.now(timezone.utc)
        assignments = ["revoked_at=COALESCE(revoked_at, :now)", "active_household_id=NULL"]
        if "updated_at" in session_columns:
            assignments.append("updated_at=:now")
        conn.execute(
            text(
                "UPDATE server_sessions SET " + ", ".join(assignments)
                + " WHERE CAST(active_household_id AS TEXT)=:household_id"
            ),
            {"now": now, "household_id": target},
        )

    for table_name in order:
        predicate = _target_predicate(
            conn,
            table_name=table_name,
            alias="target",
            target_tables=target_tables,
            edges=edges,
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

    registry_columns = _columns(conn, "household_registry")
    registry_id = _pick(registry_columns, "id", "household_id")
    if not registry_id:
        raise HouseholdLifecycleConflictError("Huishoudregister wijkt af; verwijderen is afgebroken.")

    result = conn.execute(
        text(
            f"DELETE FROM household_registry WHERE CAST({registry_id} AS TEXT)=:household_id"
        ),
        {"household_id": target},
    )
    if int(result.rowcount or 0) != 1:
        raise HouseholdLifecycleConflictError("Huishouden kon niet eenduidig worden verwijderd.")

    # Clean the historical mirror only when it exists and uses the same identity.
    if inspect(conn).has_table("households"):
        legacy_columns = _columns(conn, "households")
        legacy_id = _pick(legacy_columns, "id", "household_id")
        if legacy_id:
            conn.execute(
                text(
                    f"DELETE FROM households WHERE CAST({legacy_id} AS TEXT)=:household_id"
                ),
                {"household_id": target},
            )

    return {
        "deleted": True,
        "household_id": target,
        "household_name": str(eligibility.get("household_name") or "Huishouden"),
        "deleted_row_count": sum(deleted_by_table.values()) + 1,
        "deleted_by_table": dict(sorted(deleted_by_table.items())),
    }
