"""Server-side session storage for Rezzerv.

This module is intentionally independent from browser state. It stores only a
cryptographic hash of the opaque session identifier and resolves user,
household and membership context from the database on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from typing import Any, Literal, Mapping, cast

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
    permissions_for_session_role,
    resolve_active_platform_role_keys,
)
from app.services.authorization_membership_service import (
    canonical_role_to_runtime_role,
    resolve_effective_household_role,
)
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_PLATFORM_ROLE,
    is_frontteam_personal_household,
    is_legacy_frontteam_household,
)
from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)

SESSION_COOKIE_NAME = "rezzerv_session"
DEFAULT_SESSION_TTL = timedelta(hours=12)
REGRESSION_TEST_ADMIN_EMAIL = "test-admin@rezzerv.local"
SESSION_CONTEXT_TYPES = frozenset({"none", "regular", "system"})
SYSTEM_PLATFORM_ROLES = frozenset({"platform.superuser", "platform.ip_owner"})
SessionContextType = Literal["none", "regular", "system"]

_SERVER_SESSION_COLUMNS = (
    "id",
    "session_token_hash",
    "user_id",
    "active_household_id",
    "issued_at",
    "expires_at",
    "session_version",
    "revoked_at",
    "replaced_by_session_id",
    "created_at",
    "updated_at",
)
_SERVER_SESSION_COLUMN_CONTRACT = (
    ("id", "VARCHAR(64)", False, None, 1),
    ("session_token_hash", "VARCHAR(64)", True, None, 0),
    ("user_id", "VARCHAR(64)", True, None, 0),
    ("active_household_id", "VARCHAR(64)", None, None, 0),
    ("issued_at", "TIMESTAMP", True, None, 0),
    ("expires_at", "TIMESTAMP", True, None, 0),
    ("session_version", "INTEGER", True, "1", 0),
    ("revoked_at", "TIMESTAMP", False, None, 0),
    ("replaced_by_session_id", "VARCHAR(64)", False, None, 0),
    ("created_at", "TIMESTAMP", True, "CURRENT_TIMESTAMP", 0),
    ("updated_at", "TIMESTAMP", True, "CURRENT_TIMESTAMP", 0),
)
_SERVER_SESSION_ACTIVE_INDEX_COLUMNS = (
    "user_id",
    "revoked_at",
    "expires_at",
)
_SERVER_SESSION_TABLE_SQL = """
    CREATE TABLE {table_name} (
        id VARCHAR(64) PRIMARY KEY,
        session_token_hash VARCHAR(64) NOT NULL UNIQUE,
        user_id VARCHAR(64) NOT NULL,
        active_household_id VARCHAR(64) NULL,
        issued_at TIMESTAMP NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        session_version INTEGER NOT NULL DEFAULT 1,
        revoked_at TIMESTAMP NULL,
        replaced_by_session_id VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""


@dataclass(frozen=True)
class ServerSessionContext:
    session_id: str
    user_id: str
    email: str
    active_household_id: str | None
    context_type: SessionContextType
    role: str | None
    session_version: int
    issued_at: datetime
    expires_at: datetime
    is_platform_superuser: bool = False
    is_platform_admin: bool = False
    is_ip_owner: bool = False
    is_frontteam: bool = False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    if not normalized:
        raise ValueError("session_id ontbreekt")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def new_opaque_session_id() -> str:
    return secrets.token_urlsafe(48)


def _membership_columns(conn: Connection) -> set[str]:
    return {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("household_memberships")
    }


def membership_user_join_condition(
    conn: Connection,
    *,
    membership_alias: str = "hm",
    user_alias: str = "u",
) -> str:
    columns = _membership_columns(conn)
    if "user_email" in columns:
        return (
            f"lower(trim({membership_alias}.user_email)) = "
            f"lower(trim({user_alias}.email))"
        )
    if "user_id" in columns:
        return f"{membership_alias}.user_id = {user_alias}.id"
    raise RuntimeError("household_memberships mist zowel user_email als user_id")


def membership_active_condition(
    conn: Connection,
    *,
    membership_alias: str = "hm",
) -> str:
    columns = _membership_columns(conn)
    if "status" in columns:
        return f"lower(trim(COALESCE({membership_alias}.status, 'active'))) = 'active'"
    return "1 = 1"


def membership_id_expression(
    conn: Connection,
    *,
    membership_alias: str = "hm",
) -> str:
    columns = _membership_columns(conn)
    for column in ("id", "membership_id", "user_id", "user_email"):
        if column in columns:
            return f"CAST({membership_alias}.{column} AS TEXT)"
    raise RuntimeError("household_memberships mist een bruikbare lidmaatschapsidentiteit")


def _has_active_regular_household_membership(
    conn: Connection,
    *,
    user_id: str,
) -> bool:
    inspector = inspect(conn)
    if not inspector.has_table("household_memberships"):
        return False

    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    registry_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("household_registry")
    } if inspector.has_table("household_registry") else set()
    registry_id_column = (
        "id" if "id" in registry_columns else
        "household_id" if "household_id" in registry_columns else
        None
    )

    if registry_id_column and "context_type" in registry_columns:
        value = conn.execute(text(f"""
            SELECT 1
            FROM household_memberships hm
            JOIN app_users u ON {join_condition}
            JOIN household_registry hr
              ON CAST(hr.{registry_id_column} AS TEXT) = CAST(hm.household_id AS TEXT)
            WHERE u.id = :user_id
              AND {active_condition}
              AND lower(trim(COALESCE(hr.context_type, ''))) = 'regular'
            LIMIT 1
        """), {"user_id": str(user_id)}).first()
        return bool(value)

    value = conn.execute(text(f"""
        SELECT 1
        FROM household_memberships hm
        JOIN app_users u ON {join_condition}
        WHERE u.id = :user_id
          AND {active_condition}
          AND CAST(hm.household_id AS TEXT) <> :system_household_id
        LIMIT 1
    """), {
        "user_id": str(user_id),
        "system_household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
    }).first()
    return bool(value)


def _test_household_zero_enabled() -> bool:
    return str(
        os.getenv("REZZERV_PROVISION_TEST_HOUSEHOLD_ZERO", "false") or "false"
    ).strip().lower() in {"1", "true", "yes", "on"}


def _household_zero_allowed(*, household_id: str, email: str, role: str) -> bool:
    if household_id != SUPERGEBRUIKER_HUISHOUDEN_ID:
        return True

    normalized_email = str(email or "").strip().lower()
    normalized_role = str(role or "").strip().lower()
    return (
        _test_household_zero_enabled()
        and normalized_email == REGRESSION_TEST_ADMIN_EMAIL
        and normalized_role == "owner"
    )


def _resolve_platform_context_roles(
    conn: Connection,
    *,
    user_id: str,
    email: str,
) -> tuple[frozenset[str], frozenset[str]]:
    platform_roles = resolve_active_platform_role_keys(conn, user_id)
    system_roles = frozenset(platform_roles & SYSTEM_PLATFORM_ROLES)
    normalized_email = str(email or "").strip().lower()

    # The historical fixed e-mail address remains reserved for the canonical
    # Superuser identity, but it never grants authority by itself.
    if (
        normalized_email == SUPERGEBRUIKER_EMAIL
        and "platform.superuser" not in platform_roles
    ):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    if system_roles and FRONTTEAM_PLATFORM_ROLE in platform_roles:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    if "platform.platform_admin" in platform_roles:
        if FRONTTEAM_PLATFORM_ROLE in platform_roles:
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        if system_roles and system_roles != frozenset({"platform.superuser"}):
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        if (
            system_roles == frozenset({"platform.superuser"})
            and _has_active_regular_household_membership(
                conn,
                user_id=user_id,
            )
        ):
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
    return platform_roles, system_roles


def _sqlite_schema_objects(conn: Connection, object_type: str) -> list[Mapping[str, Any]]:
    return list(conn.execute(text("""
        SELECT name, sql
        FROM sqlite_master
        WHERE type = :object_type AND tbl_name = 'server_sessions'
          AND sql IS NOT NULL
        ORDER BY name
    """), {"object_type": object_type}).mappings())


def _sqlite_incoming_server_session_foreign_keys(conn: Connection) -> list[str]:
    incoming: list[str] = []
    table_names = conn.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
    """)).scalars()
    for table_name in table_names:
        escaped_name = str(table_name).replace('"', '""')
        foreign_keys = conn.exec_driver_sql(
            f'PRAGMA foreign_key_list("{escaped_name}")'
        ).mappings()
        if any(str(item.get("table") or "").lower() == "server_sessions" for item in foreign_keys):
            incoming.append(str(table_name))
    return incoming


def _sqlite_pragma_rows(
    conn: Connection,
    pragma_name: str,
    object_name: str,
) -> list[Mapping[str, Any]]:
    escaped_name = str(object_name).replace('"', '""')
    return list(conn.exec_driver_sql(
        f'PRAGMA {pragma_name}("{escaped_name}")'
    ).mappings())


def _validate_server_session_columns(conn: Connection, *, nullable_household: bool) -> None:
    actual_columns = _sqlite_pragma_rows(conn, "table_info", "server_sessions")
    expected_columns = []
    for name, declared_type, not_null, default, primary_key_position in (
        _SERVER_SESSION_COLUMN_CONTRACT
    ):
        expected_not_null = (
            not nullable_household if name == "active_household_id" else not_null
        )
        expected_columns.append((
            name,
            declared_type,
            bool(expected_not_null),
            default,
            primary_key_position,
        ))
    actual_contract = [
        (
            str(column.get("name") or ""),
            str(column.get("type") or "").upper(),
            bool(column.get("notnull")),
            None if column.get("dflt_value") is None else str(column["dflt_value"]),
            int(column.get("pk") or 0),
        )
        for column in actual_columns
    ]
    if actual_contract != expected_columns:
        raise RuntimeError("Onverwacht server_sessions-kolomcontract")


def _validate_server_session_unique_contract(conn: Connection) -> None:
    indexes = _sqlite_pragma_rows(conn, "index_list", "server_sessions")
    unique_contracts = []
    for index in indexes:
        if not bool(index.get("unique")):
            continue
        index_name = str(index.get("name") or "")
        columns = tuple(
            str(column.get("name") or "")
            for column in _sqlite_pragma_rows(conn, "index_info", index_name)
        )
        unique_contracts.append((str(index.get("origin") or ""), columns))
    if sorted(unique_contracts) != sorted((
        ("pk", ("id",)),
        ("u", ("session_token_hash",)),
    )):
        raise RuntimeError("Onverwacht server_sessions-UNIQUE/PK-contract")


def _validate_server_session_active_index(conn: Connection) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in _sqlite_pragma_rows(conn, "index_list", "server_sessions")
    }
    index = indexes.get("idx_server_sessions_user_active")
    if not index or bool(index.get("unique")) or bool(index.get("partial")):
        raise RuntimeError("Ongeldige idx_server_sessions_user_active")
    columns = tuple(
        str(column.get("name") or "")
        for column in _sqlite_pragma_rows(
            conn,
            "index_info",
            "idx_server_sessions_user_active",
        )
    )
    if columns != _SERVER_SESSION_ACTIVE_INDEX_COLUMNS:
        raise RuntimeError("Ongeldige idx_server_sessions_user_active-kolommen")


def _validate_server_session_schema(conn: Connection, *, nullable_household: bool) -> None:
    _validate_server_session_columns(
        conn,
        nullable_household=nullable_household,
    )
    _validate_server_session_unique_contract(conn)
    _validate_server_session_active_index(conn)


def _upgrade_server_sessions_active_household_nullable(conn: Connection) -> None:
    if conn.dialect.name != "sqlite":
        raise RuntimeError(
            "Nullable active_household_id-upgrade is alleen voor SQLite geïmplementeerd"
        )
    _validate_server_session_schema(conn, nullable_household=False)
    if inspect(conn).get_foreign_keys("server_sessions"):
        raise RuntimeError("server_sessions bevat onverwachte foreign keys")
    incoming_foreign_keys = _sqlite_incoming_server_session_foreign_keys(conn)
    if incoming_foreign_keys:
        raise RuntimeError(
            "Onverwachte inkomende server_sessions-foreign keys: "
            + ", ".join(sorted(incoming_foreign_keys))
        )
    if _sqlite_schema_objects(conn, "trigger"):
        raise RuntimeError("server_sessions bevat onverwachte triggers")
    dependent_views = conn.execute(text("""
        SELECT name FROM sqlite_master
        WHERE type = 'view' AND lower(sql) LIKE '%server_sessions%'
    """)).scalars().all()
    if dependent_views:
        raise RuntimeError(
            "Onverwachte server_sessions-views: " + ", ".join(sorted(dependent_views))
        )

    user_indexes = _sqlite_schema_objects(conn, "index")
    expected_index_names = {"idx_server_sessions_user_active"}
    unexpected_indexes = {
        str(item["name"]) for item in user_indexes
    } - expected_index_names
    if unexpected_indexes:
        raise RuntimeError(
            "Onverwachte server_sessions-indexen: "
            + ", ".join(sorted(unexpected_indexes))
        )

    temporary_table = "server_sessions__context_foundation"
    if inspect(conn).has_table(temporary_table):
        raise RuntimeError(
            "Tijdelijke server_sessions-contextfoundationtabel bestaat al"
        )
    column_list = ", ".join(_SERVER_SESSION_COLUMNS)
    with conn.begin_nested():
        conn.execute(text(_SERVER_SESSION_TABLE_SQL.format(table_name=temporary_table)))
        before_count = int(conn.execute(text(
            "SELECT COUNT(*) FROM server_sessions"
        )).scalar_one())
        conn.execute(text(f"""
            INSERT INTO {temporary_table} ({column_list})
            SELECT {column_list} FROM server_sessions
        """))
        copied_count = int(conn.execute(text(
            f"SELECT COUNT(*) FROM {temporary_table}"
        )).scalar_one())
        if copied_count != before_count:
            raise RuntimeError("server_sessions-rowcount wijkt af tijdens schema-upgrade")
        differences = int(conn.execute(text(f"""
            SELECT COUNT(*) FROM (
                SELECT {column_list} FROM server_sessions
                EXCEPT
                SELECT {column_list} FROM {temporary_table}
            )
        """)).scalar_one())
        if differences:
            raise RuntimeError("server_sessions-data wijkt af tijdens schema-upgrade")

        conn.execute(text("DROP TABLE server_sessions"))
        conn.execute(text(
            f"ALTER TABLE {temporary_table} RENAME TO server_sessions"
        ))
        conn.execute(text("""
            CREATE INDEX idx_server_sessions_user_active
            ON server_sessions(user_id, revoked_at, expires_at)
        """))
        _validate_server_session_schema(conn, nullable_household=True)
        after_count = int(conn.execute(text(
            "SELECT COUNT(*) FROM server_sessions"
        )).scalar_one())
        if after_count != before_count:
            raise RuntimeError("server_sessions-rowcount wijkt af na schema-upgrade")


def ensure_server_session_schema(conn: Connection) -> None:
    table_existed = inspect(conn).has_table("server_sessions")
    conn.execute(text(_SERVER_SESSION_TABLE_SQL.format(
        table_name="IF NOT EXISTS server_sessions"
    )))
    if not table_existed:
        conn.execute(text("""
            CREATE INDEX idx_server_sessions_user_active
            ON server_sessions(user_id, revoked_at, expires_at)
        """))
    household_column = next(
        column
        for column in _sqlite_pragma_rows(conn, "table_info", "server_sessions")
        if column["name"] == "active_household_id"
    )
    nullable_household = not bool(household_column.get("notnull"))
    _validate_server_session_schema(
        conn,
        nullable_household=nullable_household,
    )
    if not nullable_household:
        _upgrade_server_sessions_active_household_nullable(conn)


def resolve_session_context_type(
    conn: Connection,
    active_household_id: str | None,
) -> SessionContextType:
    if active_household_id is None:
        return "none"
    household_id = str(active_household_id).strip()
    if not household_id:
        raise HTTPException(status_code=403, detail="Actieve context ontbreekt")
    if not inspect(conn).has_table("household_registry"):
        raise HTTPException(status_code=403, detail="Actieve context is ongeldig")
    context_type = conn.execute(text("""
        SELECT context_type FROM household_registry
        WHERE id = :household_id
        LIMIT 1
    """), {"household_id": household_id}).scalar()
    normalized = str(context_type or "").strip().lower()
    if normalized not in {"regular", "system"}:
        raise HTTPException(status_code=403, detail="Actieve context is ongeldig")
    return cast(SessionContextType, normalized)


def _normalize_database_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_server_session(
    conn: Connection,
    *,
    user_id: str,
    active_household_id: str,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    replace_existing: bool = True,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    ensure_server_session_schema(conn)
    user_id = str(user_id or "").strip()
    household_id = str(active_household_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")
    if not household_id:
        raise HTTPException(status_code=403, detail="Actief huishouden ontbreekt")

    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    membership_id_sql = membership_id_expression(conn)
    membership = conn.execute(text(f"""
        SELECT u.id AS user_id, u.email, hm.role,
               {membership_id_sql} AS membership_id
        FROM app_users u
        JOIN household_memberships hm ON {join_condition}
        WHERE u.id = :user_id
          AND hm.household_id = :household_id
          AND {active_condition}
        LIMIT 1
    """), {"user_id": user_id, "household_id": household_id}).mappings().first()
    if not membership:
        raise HTTPException(status_code=403, detail="Geen toegang tot dit huishouden")

    membership_email = str(membership.get("email") or "")
    platform_roles, system_roles = _resolve_platform_context_roles(
        conn,
        user_id=user_id,
        email=membership_email,
    )
    if "platform.platform_admin" in platform_roles or system_roles:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    if is_legacy_frontteam_household(household_id):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    is_frontteam = FRONTTEAM_PLATFORM_ROLE in platform_roles
    is_personal_frontteam_household = is_frontteam_personal_household(
        conn,
        user_id=user_id,
        household_id=household_id,
    )
    if is_frontteam != is_personal_frontteam_household:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    effective_role_key = resolve_effective_household_role(
        conn,
        household_id=household_id,
        membership_id=str(membership.get("membership_id") or ""),
        legacy_role=membership.get("role"),
    )
    membership_role = canonical_role_to_runtime_role(effective_role_key or "") or ""
    if not membership_role:
        raise HTTPException(status_code=403, detail="Bevoegdheid ontbreekt")
    if not _household_zero_allowed(
        household_id=household_id,
        email=membership_email,
        role=membership_role,
    ):
        raise HTTPException(status_code=403, detail="Ongeldig actief huishouden")
    context_type = resolve_session_context_type(conn, household_id)
    if is_frontteam and (
        context_type != "regular"
        or not is_personal_frontteam_household
        or membership_role != "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    return _insert_server_session(
        conn,
        user_id=user_id,
        email=membership_email,
        active_household_id=household_id,
        context_type=context_type,
        role=membership_role,
        ttl=ttl,
        replace_existing=replace_existing,
        now=now,
        is_frontteam=is_frontteam,
    )


def _insert_server_session(
    conn: Connection,
    *,
    user_id: str,
    email: str,
    active_household_id: str | None,
    context_type: SessionContextType,
    role: str | None,
    ttl: timedelta,
    replace_existing: bool,
    now: datetime | None,
    is_platform_superuser: bool = False,
    is_platform_admin: bool = False,
    is_ip_owner: bool = False,
    is_frontteam: bool = False,
) -> tuple[str, ServerSessionContext]:
    issued_at = (now or utc_now()).astimezone(timezone.utc)
    expires_at = issued_at + ttl
    raw_session_id = new_opaque_session_id()
    token_hash = hash_session_id(raw_session_id)
    record_id = secrets.token_hex(32)

    if replace_existing:
        conn.execute(text("""
            UPDATE server_sessions
            SET revoked_at = :now, updated_at = :now
            WHERE user_id = :user_id
              AND revoked_at IS NULL
              AND expires_at > :now
        """), {"user_id": user_id, "now": issued_at})

    conn.execute(text("""
        INSERT INTO server_sessions (
            id, session_token_hash, user_id, active_household_id,
            issued_at, expires_at, session_version, revoked_at,
            replaced_by_session_id, created_at, updated_at
        ) VALUES (
            :id, :token_hash, :user_id, :household_id,
            :issued_at, :expires_at, 1, NULL, NULL,
            :issued_at, :issued_at
        )
    """), {
        "id": record_id,
        "token_hash": token_hash,
        "user_id": user_id,
        "household_id": active_household_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
    })

    return raw_session_id, ServerSessionContext(
        session_id=record_id,
        user_id=user_id,
        email=email,
        active_household_id=active_household_id,
        context_type=context_type,
        role=role,
        session_version=1,
        issued_at=issued_at,
        expires_at=expires_at,
        is_platform_superuser=is_platform_superuser,
        is_platform_admin=is_platform_admin,
        is_ip_owner=is_ip_owner,
        is_frontteam=is_frontteam,
    )


def _require_platform_admin_none_context(
    conn: Connection,
    *,
    user_id: str,
    email: str,
) -> None:
    platform_roles, system_roles = _resolve_platform_context_roles(
        conn,
        user_id=user_id,
        email=email,
    )
    if "platform.platform_admin" not in platform_roles or system_roles:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )


def create_none_server_session(
    conn: Connection,
    *,
    user_id: str,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    replace_existing: bool = True,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    ensure_server_session_schema(conn)
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")
    user = conn.execute(text("""
        SELECT id AS user_id, email
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")
    email = str(user.get("email") or "")
    _require_platform_admin_none_context(
        conn,
        user_id=normalized_user_id,
        email=email,
    )
    return _insert_server_session(
        conn,
        user_id=normalized_user_id,
        email=email,
        active_household_id=None,
        context_type="none",
        role=None,
        ttl=ttl,
        replace_existing=replace_existing,
        now=now,
        is_platform_admin=True,
    )


def create_system_server_session(
    conn: Connection,
    *,
    user_id: str,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    replace_existing: bool = True,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    ensure_server_session_schema(conn)
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")
    user = conn.execute(text("""
        SELECT id AS user_id, email
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).mappings().first()
    if not user:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")

    email = str(user.get("email") or "")
    platform_roles, system_roles = _resolve_platform_context_roles(
        conn,
        user_id=normalized_user_id,
        email=email,
    )
    if not system_roles:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    context_type = resolve_session_context_type(
        conn,
        SUPERGEBRUIKER_HUISHOUDEN_ID,
    )
    if context_type != "system":
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    return _insert_server_session(
        conn,
        user_id=normalized_user_id,
        email=email,
        active_household_id=SUPERGEBRUIKER_HUISHOUDEN_ID,
        context_type="system",
        role="owner",
        ttl=ttl,
        replace_existing=replace_existing,
        now=now,
        is_platform_superuser="platform.superuser" in system_roles,
        is_platform_admin="platform.platform_admin" in platform_roles,
        is_ip_owner="platform.ip_owner" in system_roles,
    )


def resolve_server_session(
    conn: Connection,
    raw_session_id: str | None,
    *,
    now: datetime | None = None,
) -> ServerSessionContext:
    if not raw_session_id:
        raise HTTPException(status_code=401, detail="Geen geldige sessie")
    ensure_server_session_schema(conn)
    current_time = (now or utc_now()).astimezone(timezone.utc)
    row = conn.execute(text("""
        SELECT
            s.id AS session_id,
            s.user_id,
            u.email,
            s.active_household_id,
            s.session_version,
            s.issued_at,
            s.expires_at,
            s.revoked_at
        FROM server_sessions s
        JOIN app_users u ON u.id = s.user_id
        WHERE s.session_token_hash = :token_hash
        LIMIT 1
    """), {"token_hash": hash_session_id(raw_session_id)}).mappings().first()

    if not row or row.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Sessie is ongeldig")
    expires_at = _normalize_database_datetime(row.get("expires_at"))
    if expires_at <= current_time:
        conn.execute(
            text("UPDATE server_sessions SET revoked_at = :now, updated_at = :now WHERE id = :id"),
            {"now": current_time, "id": row.get("session_id")},
        )
        raise HTTPException(status_code=401, detail="Sessie is verlopen")

    user_id = str(row.get("user_id") or "")
    email = str(row.get("email") or "")
    platform_roles, system_roles = _resolve_platform_context_roles(
        conn,
        user_id=user_id,
        email=email,
    )
    raw_household_id = row.get("active_household_id")
    if raw_household_id is None:
        if "platform.platform_admin" not in platform_roles or system_roles:
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        return ServerSessionContext(
            session_id=str(row.get("session_id")),
            user_id=user_id,
            email=email,
            active_household_id=None,
            context_type="none",
            role=None,
            session_version=int(row.get("session_version") or 1),
            issued_at=_normalize_database_datetime(row.get("issued_at")),
            expires_at=expires_at,
            is_platform_admin=True,
        )

    household_id = str(raw_household_id).strip()
    if not household_id:
        raise HTTPException(status_code=403, detail="Actief huishouden ontbreekt")

    if household_id == SUPERGEBRUIKER_HUISHOUDEN_ID and system_roles:
        context_type = resolve_session_context_type(conn, household_id)
        if context_type != "system":
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        return ServerSessionContext(
            session_id=str(row.get("session_id")),
            user_id=user_id,
            email=email,
            active_household_id=household_id,
            context_type="system",
            role="owner",
            session_version=int(row.get("session_version") or 1),
            issued_at=_normalize_database_datetime(row.get("issued_at")),
            expires_at=expires_at,
            is_platform_superuser="platform.superuser" in system_roles,
            is_platform_admin="platform.platform_admin" in platform_roles,
            is_ip_owner="platform.ip_owner" in system_roles,
        )

    if "platform.platform_admin" in platform_roles or system_roles:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    if is_legacy_frontteam_household(household_id):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )
    is_frontteam = FRONTTEAM_PLATFORM_ROLE in platform_roles
    is_personal_frontteam_household = is_frontteam_personal_household(
        conn,
        user_id=user_id,
        household_id=household_id,
    )
    if is_frontteam != is_personal_frontteam_household:
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    membership_id_sql = membership_id_expression(conn)
    membership = conn.execute(text(f"""
        SELECT hm.role, {membership_id_sql} AS membership_id
        FROM household_memberships hm
        JOIN app_users u ON {join_condition}
        WHERE u.id = :user_id
          AND hm.household_id = :household_id
          AND {active_condition}
        LIMIT 1
    """), {
        "user_id": user_id,
        "household_id": household_id,
    }).mappings().first()
    if not membership:
        if household_id == SUPERGEBRUIKER_HUISHOUDEN_ID:
            raise HTTPException(
                status_code=403,
                detail="Geen geldige accountcontext beschikbaar.",
            )
        raise HTTPException(status_code=401, detail="Sessie is ongeldig")
    effective_role_key = resolve_effective_household_role(
        conn,
        household_id=household_id,
        membership_id=str(membership.get("membership_id") or ""),
        legacy_role=membership.get("role"),
    )
    role = canonical_role_to_runtime_role(effective_role_key or "") or ""
    if not role:
        raise HTTPException(status_code=403, detail="Bevoegdheid ontbreekt")
    if not _household_zero_allowed(household_id=household_id, email=email, role=role):
        raise HTTPException(status_code=403, detail="Ongeldig actief huishouden")
    context_type = resolve_session_context_type(conn, household_id)
    if is_frontteam and (
        context_type != "regular"
        or not is_personal_frontteam_household
        or role != "admin"
    ):
        raise HTTPException(
            status_code=403,
            detail="Geen geldige accountcontext beschikbaar.",
        )

    return ServerSessionContext(
        session_id=str(row.get("session_id")),
        user_id=user_id,
        email=email,
        active_household_id=household_id,
        context_type=context_type,
        role=role,
        session_version=int(row.get("session_version") or 1),
        issued_at=_normalize_database_datetime(row.get("issued_at")),
        expires_at=expires_at,
        is_frontteam=is_frontteam,
    )


def revoke_server_session(conn: Connection, raw_session_id: str | None, *, now: datetime | None = None) -> None:
    if not raw_session_id:
        return
    current_time = (now or utc_now()).astimezone(timezone.utc)
    ensure_server_session_schema(conn)
    conn.execute(text("""
        UPDATE server_sessions
        SET revoked_at = COALESCE(revoked_at, :now), updated_at = :now
        WHERE session_token_hash = :token_hash
    """), {"now": current_time, "token_hash": hash_session_id(raw_session_id)})


def rotate_active_household(
    conn: Connection,
    raw_session_id: str,
    new_household_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    current = resolve_server_session(conn, raw_session_id, now=now)
    new_household_id = str(new_household_id or "").strip()
    if not new_household_id:
        raise HTTPException(status_code=403, detail="Ongeldig huishouden")

    raw_new_session_id, new_context = create_server_session(
        conn,
        user_id=current.user_id,
        active_household_id=new_household_id,
        replace_existing=False,
        now=now,
    )
    current_time = (now or utc_now()).astimezone(timezone.utc)
    conn.execute(text("""
        UPDATE server_sessions
        SET revoked_at = :now,
            replaced_by_session_id = :replacement_id,
            updated_at = :now
        WHERE id = :session_id
    """), {
        "now": current_time,
        "replacement_id": new_context.session_id,
        "session_id": current.session_id,
    })
    return raw_new_session_id, new_context


def public_session_payload(context: ServerSessionContext) -> Mapping[str, Any]:
    if context.context_type == "none":
        granted_permissions = set(ROLE_PERMISSIONS["platform.platform_admin"])
        permissions = {key: True for key in sorted(granted_permissions)}
        return {
            "user": {"id": context.user_id, "email": context.email},
            "user_id": context.user_id,
            "email": context.email,
            "active_household_id": None,
            "active_household_name": "",
            "context_type": context.context_type,
            "role": None,
            "display_role": None,
            "permissions": permissions,
            "supported_permissions": sorted(granted_permissions),
            "can_manage_member_permissions": False,
            "can_manage_members": False,
            "is_viewer": False,
            "is_platform_superuser": False,
            "is_frontteam": False,
            "session_version": context.session_version,
            "expires_at": context.expires_at.isoformat(),
        }
    platform_superuser = bool(context.is_platform_superuser)
    platform_admin = bool(context.is_platform_admin)
    platform_ip_owner = bool(context.is_ip_owner)
    platform_frontteam = bool(context.is_frontteam)
    granted_permissions = permissions_for_session_role(
        context.role,
        platform_superuser=platform_superuser,
    )
    if platform_admin:
        granted_permissions.update(ROLE_PERMISSIONS["platform.platform_admin"])
    if platform_ip_owner:
        granted_permissions.update(ROLE_PERMISSIONS["platform.ip_owner"])
    if platform_frontteam:
        granted_permissions.update(ROLE_PERMISSIONS[FRONTTEAM_PLATFORM_ROLE])
    permissions = {key: True for key in sorted(granted_permissions)}
    role = str(context.role or "").strip().lower()
    if context.active_household_id == SUPERGEBRUIKER_HUISHOUDEN_ID:
        active_household_name = "Systeemhuishouden"
    else:
        active_household_name = ""
    return {
        "user": {"id": context.user_id, "email": context.email},
        "user_id": context.user_id,
        "email": context.email,
        "active_household_id": context.active_household_id,
        "active_household_name": active_household_name,
        "context_type": context.context_type,
        "role": role,
        "display_role": role,
        "permissions": permissions,
        "supported_permissions": sorted(granted_permissions),
        "can_manage_member_permissions": bool(permissions.get("permissions.manage")),
        "can_manage_members": bool(permissions.get("members.manage")),
        "is_viewer": role == "viewer",
        "is_platform_superuser": platform_superuser,
        "is_frontteam": platform_frontteam,
        "session_version": context.session_version,
        "expires_at": context.expires_at.isoformat(),
    }
