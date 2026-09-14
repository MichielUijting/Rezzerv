"""Canonical persistent platform feature-flag registry.

Feature flags are platform-wide availability controls, not authorization.
Existing permission checks remain authoritative and must run independently.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from fastapi import HTTPException

from app.services.authorization_foundation_service import write_authorization_audit


FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH = "external_product_search"
FEATURE_GERECHTEN = "feature.gerechten"

FEATURE_FLAG_DEFINITIONS = {
    FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH: {
        "category": "technical",
        "label": "Externe productzoekfunctie",
        "description": (
            "Schakelt platformbreed de externe productzoekroutes die onder "
            "platform.external_products.search vallen."
        ),
        "default_enabled": True,
    },
    FEATURE_GERECHTEN: {
        "category": "functional",
        "label": "Gerechten",
        "description": "Bepaalt of Gerechten wereldwijd beschikbaar is in Rezzerv.",
        "default_enabled": False,
    },
}


def require_feature_category(flag_key: str, category: str) -> None:
    """Fail closed on unknown keys and keys outside the endpoint's category."""
    _, definition = _definition(flag_key)
    if definition.get("category") != category:
        raise KeyError(flag_key)


def require_platform_feature_enabled(conn: Connection, flag_key: str) -> None:
    """Availability check to run after a route's normal session/permission checks."""
    if not is_platform_feature_enabled(conn, flag_key):
        _, definition = _definition(flag_key)
        raise HTTPException(
            status_code=503,
            detail=f"{definition['label']} is platformbreed uitgeschakeld",
        )


def validate_platform_feature_flag_schema(conn: Connection) -> None:
    """Fail closed when Alembic has not installed the feature-flag table."""

    inspector = inspect(conn)
    if not inspector.has_table("platform_feature_flags"):
        raise RuntimeError("platform_feature_flags is niet gemigreerd")
    required_columns = {"flag_key", "enabled", "updated_by", "updated_at"}
    columns = {
        str(column.get("name") or "").strip().lower(): column
        for column in inspector.get_columns("platform_feature_flags")
    }
    missing_columns = sorted(required_columns - set(columns))
    if missing_columns:
        raise RuntimeError(
            "platform_feature_flags schema drift; ontbrekende kolommen: "
            + ", ".join(missing_columns)
        )
    primary_key = tuple(
        inspector.get_pk_constraint("platform_feature_flags").get("constrained_columns") or ()
    )
    if primary_key != ("flag_key",):
        raise RuntimeError(
            "platform_feature_flags schema drift; onjuiste primary key: "
            f"{primary_key!r}"
        )
    if conn.dialect.name == "postgresql":
        if not isinstance(columns["enabled"]["type"], sa.Boolean):
            raise RuntimeError("platform_feature_flags.enabled moet PostgreSQL BOOLEAN zijn")
        updated_at_type = columns["updated_at"]["type"]
        if not isinstance(updated_at_type, sa.DateTime) or not bool(
            getattr(updated_at_type, "timezone", False)
        ):
            raise RuntimeError("platform_feature_flags.updated_at moet PostgreSQL TIMESTAMPTZ zijn")


def ensure_platform_feature_flag_schema(conn: Connection) -> None:
    """Validate the Alembic-owned feature-flag schema without mutating it."""

    validate_platform_feature_flag_schema(conn)


def _definition(flag_key: str) -> tuple[str, dict]:
    normalized_key = str(flag_key or "").strip()
    definition = FEATURE_FLAG_DEFINITIONS.get(normalized_key)
    if definition is None:
        raise KeyError(normalized_key)
    return normalized_key, definition


def _serialize_flag(flag_key: str, definition: dict, override: dict | None) -> dict:
    if override is None:
        enabled = bool(definition["default_enabled"])
        source = "default"
        updated_by = None
        updated_at = None
    else:
        enabled = bool(override.get("enabled"))
        source = "override"
        updated_by = str(override.get("updated_by") or "").strip() or None
        updated_at = override.get("updated_at")

    return {
        "key": flag_key,
        "label": definition["label"],
        "description": definition["description"],
        "enabled": enabled,
        "default_enabled": bool(definition["default_enabled"]),
        "source": source,
        "updated_by": updated_by,
        "updated_at": updated_at,
    }


def list_platform_feature_flags(conn: Connection, *, category: str | None = None) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT flag_key, enabled, updated_by, updated_at
            FROM platform_feature_flags
            ORDER BY flag_key ASC
            """
        )
    ).mappings().all()
    overrides = {str(row["flag_key"]): dict(row) for row in rows}
    return [
        _serialize_flag(flag_key, definition, overrides.get(flag_key))
        for flag_key, definition in FEATURE_FLAG_DEFINITIONS.items()
        if category is None or definition.get("category") == category
    ]


def get_platform_feature_flag(conn: Connection, flag_key: str) -> dict:
    normalized_key, definition = _definition(flag_key)
    row = conn.execute(
        text(
            """
            SELECT flag_key, enabled, updated_by, updated_at
            FROM platform_feature_flags
            WHERE flag_key = :flag_key
            LIMIT 1
            """
        ),
        {"flag_key": normalized_key},
    ).mappings().first()
    return _serialize_flag(normalized_key, definition, dict(row) if row else None)


def is_platform_feature_enabled(conn: Connection, flag_key: str) -> bool:
    """Read the effective value without creating schema or masking schema drift."""

    normalized_key, definition = _definition(flag_key)
    row = conn.execute(
        text(
            """
            SELECT enabled
            FROM platform_feature_flags
            WHERE flag_key = :flag_key
            LIMIT 1
            """
        ),
        {"flag_key": normalized_key},
    ).mappings().first()
    if row is None:
        return bool(definition["default_enabled"])
    return bool(row.get("enabled"))


def set_platform_feature_flag(
    conn: Connection,
    flag_key: str,
    *,
    enabled: bool,
    updated_by: str,
) -> dict:
    normalized_key, _definition_value = _definition(flag_key)
    actor_id = str(updated_by or "").strip()
    if not actor_id:
        raise ValueError("updated_by is verplicht")

    functional = _definition_value.get("category") == "functional"
    if functional:
        # Serialize even the first write (there is no row to lock yet).
        # This keeps audit old/new values correct for concurrent PostgreSQL writers.
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                         {"key": "platform_feature_flags:" + normalized_key})
        previous = is_platform_feature_enabled(conn, normalized_key)

    result = conn.execute(
        text(
            """
            UPDATE platform_feature_flags
            SET enabled = :enabled,
                updated_by = :updated_by,
                updated_at = CURRENT_TIMESTAMP
            WHERE flag_key = :flag_key
            """
        ),
        {
            "flag_key": normalized_key,
            "enabled": bool(enabled),
            "updated_by": actor_id,
        },
    )
    if result.rowcount == 0:
        conn.execute(
            text(
                """
                INSERT INTO platform_feature_flags (
                    flag_key, enabled, updated_by, updated_at
                ) VALUES (
                    :flag_key, :enabled, :updated_by, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "flag_key": normalized_key,
                "enabled": bool(enabled),
                "updated_by": actor_id,
            },
        )
    if functional and previous != bool(enabled):
        write_authorization_audit(
            conn, actor_user_id=actor_id, actor_type="platform",
            action="platform.functional_feature.updated",
            object_type="platform_feature_flag", object_id=normalized_key,
            old_value={"enabled": previous}, new_value={"enabled": bool(enabled)},
        )
    return get_platform_feature_flag(conn, normalized_key)
