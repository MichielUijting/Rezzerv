"""Provision one personal regular household for every active Frontteam user.

Frontteam is a platform role. It never receives authority from a shared
Frontteam household. Every active ``platform.frontteam`` user gets one explicit
1:1 personal regular household projection for ordinary Rezzerv usage. The
historical shared household with id ``frontteam`` is retained as data only and
is never a valid runtime context after the 9.1.5 cutover.
"""

from __future__ import annotations

from dataclasses import dataclass
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    resolve_active_platform_role_keys,
)
from app.services.household_onboarding_service import start_new_household_onboarding
from app.services.roles_v2_schema_foundation import (
    HOUSEHOLD_CONTEXT_REGULAR,
    ensure_roles_v2_account_and_household_foundation,
)

# Historical shared household. Kept only so old rows can be recognised and
# rejected/migrated without deleting household-scoped business data.
FRONTTEAM_HOUSEHOLD_ID = "frontteam"
FRONTTEAM_HOUSEHOLD_NAME = "Frontteam"
LEGACY_FRONTTEAM_HOUSEHOLD_ID = FRONTTEAM_HOUSEHOLD_ID

FRONTTEAM_PLATFORM_ROLE = "platform.frontteam"
FRONTTEAM_HOUSEHOLD_ROLE_KEY = "household.admin"
FRONTTEAM_LEGACY_ROLE = "admin"
FRONTTEAM_PERSONAL_HOUSEHOLD_NAME = "Mijn huishouden"
FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE = "frontteam_personal_households"


@dataclass(frozen=True)
class FrontteamHouseholdProvisioningResult:
    active_frontteam_users: int
    personal_household_ids: tuple[str, ...]
    households_created: int
    memberships_created: int
    memberships_updated: int
    legacy_memberships_removed: int

    @property
    def household_id(self) -> str | None:
        """Compatibility projection for callers that provision exactly one user."""
        if len(self.personal_household_ids) == 1:
            return self.personal_household_ids[0]
        return None


def _columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _pick(columns: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in columns), None)


def frontteam_personal_household_id(user_id: str) -> str:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("Frontteam-gebruiker ontbreekt")
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"rezzerv:frontteam-personal-household:{normalized_user_id}",
        )
    )


def _frontteam_membership_id(user_id: str, household_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"rezzerv:frontteam-personal-membership:{user_id}:{household_id}",
        )
    )


def ensure_frontteam_personal_household_schema(conn: Connection) -> None:
    """Validate the Alembic-owned Frontteam personal-household contract."""
    inspector = inspect(conn)
    if not inspector.has_table(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE):
        raise RuntimeError(
            "frontteam_personal_households ontbreekt; voer eerst Alembic-migraties uit"
        )
    columns = _columns(conn, FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE)
    required = {"user_id", "household_id", "created_at", "updated_at"}
    missing = required - columns
    if missing:
        raise RuntimeError(
            "frontteam_personal_households mist canonieke kolommen: "
            + ", ".join(sorted(missing))
        )
    primary_key = tuple(
        str(column or "")
        for column in (inspector.get_pk_constraint(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE).get("constrained_columns") or ())
    )
    if primary_key != ("user_id",):
        raise RuntimeError(
            "frontteam_personal_households.user_id moet de primaire sleutel zijn"
        )
    unique_sets = {
        tuple(str(column or "") for column in (constraint.get("column_names") or ()))
        for constraint in inspector.get_unique_constraints(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE)
    }
    if ("household_id",) not in unique_sets:
        raise RuntimeError(
            "frontteam_personal_households.household_id moet uniek zijn"
        )


def _active_frontteam_users(conn: Connection) -> list[dict[str, str]]:
    rows = conn.execute(text("""
        SELECT u.id AS user_id, u.email AS email
        FROM auth_platform_user_roles ur
        JOIN auth_roles r ON r.role_key = ur.role_key
        JOIN app_users u ON u.id = ur.user_id
        WHERE ur.role_key = :role_key
          AND ur.active IS TRUE
          AND r.active IS TRUE
          AND r.scope = 'platform'
        ORDER BY u.id
    """), {"role_key": FRONTTEAM_PLATFORM_ROLE}).mappings().all()
    return [
        {
            "user_id": str(row.get("user_id") or "").strip(),
            "email": str(row.get("email") or "").strip(),
        }
        for row in rows
        if str(row.get("user_id") or "").strip()
    ]


def _ensure_personal_mapping(conn: Connection, user_id: str) -> str:
    ensure_frontteam_personal_household_schema(conn)
    expected_household_id = frontteam_personal_household_id(user_id)
    conn.execute(text(f"""
        INSERT INTO {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE}(
            user_id, household_id, created_at, updated_at
        ) VALUES (
            :user_id, :household_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT(user_id) DO NOTHING
    """), {
        "user_id": user_id,
        "household_id": expected_household_id,
    })
    row = conn.execute(text(f"""
        SELECT household_id
        FROM {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE}
        WHERE user_id = :user_id
        LIMIT 1
    """), {"user_id": user_id}).mappings().first()
    household_id = str((row or {}).get("household_id") or "").strip()
    if household_id != expected_household_id:
        raise RuntimeError("Frontteam-persoonlijk huishouden wijkt af van canonieke identiteit")
    owner_count = int(conn.execute(text(f"""
        SELECT COUNT(*)
        FROM {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE}
        WHERE household_id = :household_id
    """), {"household_id": household_id}).scalar_one())
    if owner_count != 1:
        raise RuntimeError("Frontteam-persoonlijk huishouden is niet 1-op-1 gekoppeld")
    return household_id


def resolve_frontteam_personal_household_id(
    conn: Connection,
    user_id: str,
) -> str | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None
    ensure_frontteam_personal_household_schema(conn)
    value = conn.execute(text(f"""
        SELECT household_id
        FROM {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE}
        WHERE user_id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).scalar()
    normalized = str(value or "").strip()
    return normalized or None


def is_frontteam_personal_household(
    conn: Connection,
    *,
    user_id: str,
    household_id: str,
) -> bool:
    mapped = resolve_frontteam_personal_household_id(conn, user_id)
    return bool(mapped and mapped == str(household_id or "").strip())


def is_legacy_frontteam_household(household_id: str | None) -> bool:
    return str(household_id or "").strip() == LEGACY_FRONTTEAM_HOUSEHOLD_ID


def _ensure_personal_household(conn: Connection, household_id: str) -> bool:
    ensure_roles_v2_account_and_household_foundation(conn)
    columns = _columns(conn, "household_registry")
    id_column = _pick(columns, "id", "household_id")
    name_column = _pick(columns, "naam", "name")
    if not id_column or not name_column:
        raise RuntimeError("household_registry heeft geen bruikbare id-/naamkolommen")

    existing = conn.execute(text(f"""
        SELECT {('context_type' if 'context_type' in columns else "'regular'")} AS context_type
        FROM household_registry
        WHERE CAST({id_column} AS TEXT) = :household_id
        LIMIT 1
    """), {"household_id": household_id}).mappings().first()
    if existing:
        if str(existing.get("context_type") or "regular").strip().lower() != HOUSEHOLD_CONTEXT_REGULAR:
            raise RuntimeError("Frontteam-persoonlijk huishouden is niet regulier")
        return False

    insert_columns = [id_column, name_column]
    insert_values = [":household_id", ":household_name"]
    params: dict[str, object] = {
        "household_id": household_id,
        "household_name": FRONTTEAM_PERSONAL_HOUSEHOLD_NAME,
    }
    if "context_type" in columns:
        insert_columns.append("context_type")
        insert_values.append(":context_type")
        params["context_type"] = HOUSEHOLD_CONTEXT_REGULAR
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
    conn.execute(text(
        f"INSERT INTO household_registry ({', '.join(insert_columns)}) "
        f"VALUES ({', '.join(insert_values)})"
    ), params)
    start_new_household_onboarding(conn, household_id)
    return True


def _ensure_frontteam_membership(
    conn: Connection,
    *,
    user_id: str,
    email: str,
    household_id: str,
) -> tuple[str, bool]:
    columns = _columns(conn, "household_memberships")
    membership_id_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    email_column = _pick(columns, "user_email", "email")
    user_column = _pick(columns, "user_id")
    role_column = _pick(columns, "role", "rol")
    status_column = _pick(columns, "status", "membership_status")
    active_column = _pick(columns, "active", "is_active")
    if not household_column or not role_column or (not email_column and not user_column):
        raise RuntimeError("household_memberships heeft geen bruikbare lidmaatschapskolommen")

    identity_predicates: list[str] = []
    params: dict[str, object] = {
        "household_id": household_id,
        "user_id": user_id,
        "email": email,
    }
    if user_column:
        identity_predicates.append(f"CAST({user_column} AS TEXT) = :user_id")
    if email_column:
        identity_predicates.append(f"lower(trim({email_column})) = lower(trim(:email))")

    membership_id_expression = (
        f"CAST({membership_id_column} AS TEXT)"
        if membership_id_column
        else (f"CAST({user_column} AS TEXT)" if user_column else f"CAST({email_column} AS TEXT)")
    )
    existing = conn.execute(text(
        f"SELECT {membership_id_expression} AS membership_id "
        f"FROM household_memberships "
        f"WHERE CAST({household_column} AS TEXT) = :household_id "
        f"AND ({' OR '.join(identity_predicates)}) LIMIT 1"
    ), params).mappings().first()

    created = existing is None
    if existing:
        membership_id = str(existing.get("membership_id") or "").strip()
        assignments = [f"{role_column} = :legacy_role"]
        update_params = dict(params)
        update_params["legacy_role"] = FRONTTEAM_LEGACY_ROLE
        if status_column:
            assignments.append(f"{status_column} = 'active'")
        if active_column:
            assignments.append(f"{active_column} = 1")
        if "updated_at" in columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")
        conn.execute(text(
            f"UPDATE household_memberships SET {', '.join(assignments)} "
            f"WHERE CAST({household_column} AS TEXT) = :household_id "
            f"AND ({' OR '.join(identity_predicates)})"
        ), update_params)
    else:
        membership_id = (
            _frontteam_membership_id(user_id, household_id)
            if membership_id_column
            else (user_id if user_column else email)
        )
        insert_columns = [household_column, role_column]
        insert_values = [":household_id", ":legacy_role"]
        insert_params = dict(params)
        insert_params["legacy_role"] = FRONTTEAM_LEGACY_ROLE
        if membership_id_column:
            insert_columns.insert(0, membership_id_column)
            insert_values.insert(0, ":membership_id")
            insert_params["membership_id"] = membership_id
        if user_column:
            insert_columns.append(user_column)
            insert_values.append(":user_id")
        if email_column:
            insert_columns.append(email_column)
            insert_values.append(":email")
        if status_column:
            insert_columns.append(status_column)
            insert_values.append("'active'")
        if active_column:
            insert_columns.append(active_column)
            insert_values.append("1")
        if "created_at" in columns:
            insert_columns.append("created_at")
            insert_values.append("CURRENT_TIMESTAMP")
        if "updated_at" in columns:
            insert_columns.append("updated_at")
            insert_values.append("CURRENT_TIMESTAMP")
        conn.execute(text(
            f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ), insert_params)

    conn.execute(text("""
        INSERT INTO auth_membership_roles(
            household_id, membership_id, role_key, active, updated_at
        ) VALUES (
            :household_id, :membership_id, :role_key, TRUE, CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id, membership_id) DO UPDATE SET
            role_key = excluded.role_key,
            active = TRUE,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": household_id,
        "membership_id": membership_id,
        "role_key": FRONTTEAM_HOUSEHOLD_ROLE_KEY,
    })
    return membership_id, created


def _remove_legacy_shared_membership(
    conn: Connection,
    *,
    user_id: str,
    email: str,
) -> int:
    columns = _columns(conn, "household_memberships")
    if not columns:
        return 0
    membership_id_column = _pick(columns, "id", "membership_id")
    household_column = _pick(columns, "household_id", "huishouden_id")
    email_column = _pick(columns, "user_email", "email")
    user_column = _pick(columns, "user_id")
    if not household_column or (not email_column and not user_column):
        return 0

    predicates: list[str] = []
    params: dict[str, object] = {
        "household_id": LEGACY_FRONTTEAM_HOUSEHOLD_ID,
        "user_id": user_id,
        "email": email,
    }
    if user_column:
        predicates.append(f"CAST({user_column} AS TEXT) = :user_id")
    if email_column:
        predicates.append(f"lower(trim({email_column})) = lower(trim(:email))")
    membership_id_expression = (
        f"CAST({membership_id_column} AS TEXT)"
        if membership_id_column
        else (f"CAST({user_column} AS TEXT)" if user_column else f"CAST({email_column} AS TEXT)")
    )
    rows = conn.execute(text(
        f"SELECT {membership_id_expression} AS membership_id "
        f"FROM household_memberships "
        f"WHERE CAST({household_column} AS TEXT) = :household_id "
        f"AND ({' OR '.join(predicates)})"
    ), params).mappings().all()
    if not rows:
        return 0

    for row in rows:
        membership_id = str(row.get("membership_id") or "").strip()
        if membership_id:
            conn.execute(text("""
                UPDATE auth_membership_roles
                SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id
                  AND membership_id = :membership_id
            """), {
                "household_id": LEGACY_FRONTTEAM_HOUSEHOLD_ID,
                "membership_id": membership_id,
            })
    conn.execute(text(
        f"DELETE FROM household_memberships "
        f"WHERE CAST({household_column} AS TEXT) = :household_id "
        f"AND ({' OR '.join(predicates)})"
    ), params)
    return len(rows)


def ensure_frontteam_personal_household_for_user(
    conn: Connection,
    *,
    user_id: str,
    email: str,
) -> tuple[str, bool, bool, int]:
    normalized_user_id = str(user_id or "").strip()
    normalized_email = str(email or "").strip()
    if not normalized_user_id:
        raise ValueError("Frontteam-gebruiker ontbreekt")
    if FRONTTEAM_PLATFORM_ROLE not in resolve_active_platform_role_keys(conn, normalized_user_id):
        raise PermissionError("Gebruiker heeft geen actieve Frontteam-platformrol")

    household_id = _ensure_personal_mapping(conn, normalized_user_id)
    household_created = _ensure_personal_household(conn, household_id)
    _, membership_created = _ensure_frontteam_membership(
        conn,
        user_id=normalized_user_id,
        email=normalized_email,
        household_id=household_id,
    )
    removed = _remove_legacy_shared_membership(
        conn,
        user_id=normalized_user_id,
        email=normalized_email,
    )
    return household_id, household_created, membership_created, removed


def ensure_frontteam_household_for_session_runtime(
    conn: Connection,
) -> FrontteamHouseholdProvisioningResult:
    """Idempotently project every active Frontteam user into one personal household."""

    ensure_authorization_foundation(conn)
    ensure_roles_v2_account_and_household_foundation(conn)
    ensure_frontteam_personal_household_schema(conn)
    users = _active_frontteam_users(conn)
    household_ids: list[str] = []
    households_created = memberships_created = memberships_updated = 0
    legacy_memberships_removed = 0
    for user in users:
        household_id, household_created, membership_created, removed = (
            ensure_frontteam_personal_household_for_user(
                conn,
                user_id=user["user_id"],
                email=user["email"],
            )
        )
        household_ids.append(household_id)
        households_created += int(household_created)
        memberships_created += int(membership_created)
        memberships_updated += int(not membership_created)
        legacy_memberships_removed += removed

    if len(set(household_ids)) != len(household_ids):
        raise RuntimeError("Meerdere Frontteam-leden delen hetzelfde persoonlijke huishouden")

    return FrontteamHouseholdProvisioningResult(
        active_frontteam_users=len(users),
        personal_household_ids=tuple(household_ids),
        households_created=households_created,
        memberships_created=memberships_created,
        memberships_updated=memberships_updated,
        legacy_memberships_removed=legacy_memberships_removed,
    )
