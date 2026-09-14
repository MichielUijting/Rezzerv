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

ACTION_HOME_MELDINGEN = "action.home.meldingen"
ACTION_HOME_BIJNA_OP = "action.home.bijna_op"
ACTION_HOME_WINKELEN = "action.home.winkelen"
ACTION_HOME_PROGNOSES = "action.home.prognoses"
ACTION_HOME_UITLENEN = "action.home.uitlenen"
ACTION_HOME_VOORRAAD = "action.home.voorraad"
ACTION_HOME_PRODUCTGROEPEN = "action.home.productgroepen"
ACTION_HOME_UITPAKKEN = "action.home.uitpakken"
ACTION_HOME_KASSA = "action.home.kassa"
ACTION_HOME_SPAARTEGOEDEN = "action.home.spaartegoeden"
ACTION_HOME_EXTERNE_DATABASES = "action.home.externe_databases"
ACTION_HOME_CATALOGUS = "action.home.catalogus"
ACTION_HOME_KLANTKAARTEN = "action.home.klantkaarten"
ACTION_HOME_BESTELLEN = "action.home.bestellen"
ACTION_HOME_VERLENGEN = "action.home.verlengen"
ACTION_HOME_INSTELLINGEN = "action.home.instellingen"
ACTION_HOME_ADMIN = "action.home.admin"
ACTION_HOME_SUPERUSER = "action.home.superuser"


def _home_action(label: str, home_tile_key: str) -> dict:
    return {
        "category": "action_button",
        "group": "Startpagina",
        "label": label,
        "description": f"Bepaalt of {label} als actie op de Startpagina beschikbaar is.",
        "home_tile_key": home_tile_key,
        "default_enabled": True,
    }


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
        "group": "Startpagina",
        "label": "Gerechten",
        "description": "Bepaalt of Gerechten wereldwijd beschikbaar is in Rezzerv.",
        "home_tile_key": "recepten",
        "default_enabled": False,
    },
    ACTION_HOME_MELDINGEN: _home_action("Meldingen", "meldingen"),
    ACTION_HOME_BIJNA_OP: _home_action("Bijna op", "bijna-op"),
    ACTION_HOME_WINKELEN: _home_action("Winkelen", "winkelen"),
    ACTION_HOME_PROGNOSES: _home_action("Prognoses", "prognoses"),
    ACTION_HOME_UITLENEN: _home_action("Uitlenen", "uitlenen"),
    ACTION_HOME_VOORRAAD: _home_action("Voorraad", "voorraad"),
    ACTION_HOME_PRODUCTGROEPEN: _home_action("Productgroepen", "productgroepen"),
    ACTION_HOME_UITPAKKEN: _home_action("Uitpakken", "kassabonnen"),
    ACTION_HOME_KASSA: _home_action("Kassa", "kassa"),
    ACTION_HOME_SPAARTEGOEDEN: _home_action("Spaartegoeden", "spaartegoeden"),
    ACTION_HOME_EXTERNE_DATABASES: _home_action("Externe databases", "externe-databases"),
    ACTION_HOME_CATALOGUS: _home_action("Catalogus", "catalogus"),
    ACTION_HOME_KLANTKAARTEN: _home_action("Klantkaarten", "klantkaarten"),
    ACTION_HOME_BESTELLEN: _home_action("Bestellen", "bestellen"),
    ACTION_HOME_VERLENGEN: _home_action("Verlengen", "verlengen"),
    ACTION_HOME_INSTELLINGEN: _home_action("Instellingen", "instellingen"),
    ACTION_HOME_ADMIN: _home_action("Admin", "admin"),
    ACTION_HOME_SUPERUSER: _home_action("Superuser", "superuser"),
}


def require_feature_category(flag_key: str, category: str) -> None:
    """Fail closed on unknown keys and keys outside the endpoint's category."""
    _, definition = _definition(flag_key)
    if definition.get("category") != category:
        raise KeyError(flag_key)


def require_home_action(flag_key: str) -> None:
    """Fail closed unless the key represents an action on the Startpagina."""
    _, definition = _definition(flag_key)
    if not str(definition.get("home_tile_key") or "").strip():
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
        "category": definition.get("category"),
        "group": definition.get("group"),
        "label": definition["label"],
        "description": definition["description"],
        "home_tile_key": definition.get("home_tile_key"),
        "enabled": enabled,
        "default_enabled": bool(definition["default_enabled"]),
        "source": source,
        "updated_by": updated_by,
        "updated_at": updated_at,
    }


def _overrides(conn: Connection) -> dict[str, dict]:
    rows = conn.execute(
        text(
            """
            SELECT flag_key, enabled, updated_by, updated_at
            FROM platform_feature_flags
            ORDER BY flag_key ASC
            """
        )
    ).mappings().all()
    return {str(row["flag_key"]): dict(row) for row in rows}


def list_platform_feature_flags(conn: Connection, *, category: str | None = None) -> list[dict]:
    overrides = _overrides(conn)
    return [
        _serialize_flag(flag_key, definition, overrides.get(flag_key))
        for flag_key, definition in FEATURE_FLAG_DEFINITIONS.items()
        if category is None or definition.get("category") == category
    ]


def list_home_action_flags(conn: Connection) -> list[dict]:
    """Return only availability controls that belong to Startpagina actions."""
    overrides = _overrides(conn)
    return [
        _serialize_flag(flag_key, definition, overrides.get(flag_key))
        for flag_key, definition in FEATURE_FLAG_DEFINITIONS.items()
        if str(definition.get("home_tile_key") or "").strip()
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
    normalized_key, definition = _definition(flag_key)
    actor_id = str(updated_by or "").strip()
    if not actor_id:
        raise ValueError("updated_by is verplicht")

    managed_category = definition.get("category") in {"functional", "action_button"}
    if managed_category:
        # Serialize even the first write (there is no row to lock yet).
        # This keeps audit old/new values correct for concurrent PostgreSQL writers.
        if conn.dialect.name == "postgresql":
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": "platform_feature_flags:" + normalized_key},
            )
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
    if managed_category and previous != bool(enabled):
        audit_action = (
            "platform.functional_feature.updated"
            if definition.get("category") == "functional"
            else "platform.action_button.updated"
        )
        write_authorization_audit(
            conn,
            actor_user_id=actor_id,
            actor_type="platform",
            action=audit_action,
            object_type="platform_feature_flag",
            object_id=normalized_key,
            old_value={"enabled": previous},
            new_value={"enabled": bool(enabled)},
        )
    return get_platform_feature_flag(conn, normalized_key)
