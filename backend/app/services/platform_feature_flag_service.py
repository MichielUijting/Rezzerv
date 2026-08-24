"""Canonical persistent platform feature-flag registry.

Feature flags are platform-wide availability controls, not authorization.
Existing permission checks remain authoritative and must run independently.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError, ProgrammingError


FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH = "external_product_search"

FEATURE_FLAG_DEFINITIONS = {
    FEATURE_FLAG_EXTERNAL_PRODUCT_SEARCH: {
        "label": "Externe productzoekfunctie",
        "description": (
            "Schakelt platformbreed de externe productzoekroutes die onder "
            "platform.external_products.search vallen."
        ),
        "default_enabled": True,
    },
}


def ensure_platform_feature_flag_schema(conn: Connection) -> None:
    """Create only the platform-wide persistence table; do not seed overrides."""

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS platform_feature_flags (
                flag_key VARCHAR(128) PRIMARY KEY,
                enabled BOOLEAN NOT NULL,
                updated_by VARCHAR(255),
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


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


def list_platform_feature_flags(conn: Connection) -> list[dict]:
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
    """Read the effective value without ever creating schema or an override.

    During legacy-focused tests or a pre-migration process where the table is not
    present yet, the registered default is used. Production startup creates the
    table before requests are served.
    """

    normalized_key, definition = _definition(flag_key)
    try:
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
    except (OperationalError, ProgrammingError):
        return bool(definition["default_enabled"])
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
    return get_platform_feature_flag(conn, normalized_key)
