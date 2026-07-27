from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.global_product_service import get_or_create_global_product
from app.services.product_inventory_group_store import (
    ensure_product_inventory_group_schema,
    link_global_product_to_inventory_group_with_connection,
)
from app.services.product_type_manual_selection_preview_service import (
    build_product_type_manual_selection_preview,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(table_name: str) -> set[str]:
    try:
        return {str(column.get("name") or "") for column in inspect(engine).get_columns(table_name)}
    except Exception:
        return set()


def _ensure_product_identity_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS product_identities (
            id TEXT PRIMARY KEY,
            household_id TEXT,
            household_article_id TEXT NOT NULL,
            global_product_id TEXT NOT NULL,
            identity_type TEXT,
            source TEXT,
            is_primary INTEGER DEFAULT 1,
            confirmed_by_user INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """))
    existing = _columns("product_identities")
    definitions = {
        "household_id": "TEXT",
        "household_article_id": "TEXT",
        "global_product_id": "TEXT",
        "identity_type": "TEXT",
        "source": "TEXT",
        "is_primary": "INTEGER DEFAULT 1",
        "confirmed_by_user": "INTEGER DEFAULT 0",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    }
    for name, definition in definitions.items():
        if name not in existing:
            conn.execute(text(f"ALTER TABLE product_identities ADD COLUMN {name} {definition}"))


def confirm_product_type_manual_selection(
    household_id: str,
    *,
    household_article_id: str,
    gpc_brick_code: str,
    confirmed: bool,
) -> dict[str, Any]:
    """Persist one explicitly confirmed manual GPC Producttype selection.

    This creates or reuses a global product identity and stores exactly one active,
    user-confirmed Producttype membership. It never changes stock quantities and
    never creates inventory events.
    """
    if confirmed is not True:
        raise ValueError("explicit confirmation is required")

    preview = build_product_type_manual_selection_preview(
        str(household_id),
        household_article_id=household_article_id,
        gpc_brick_code=gpc_brick_code,
    )
    selected = dict(preview.get("selected_product_type") or {})
    product_type_id = str(selected.get("product_type_id") or "").strip()
    inventory_name = str(preview.get("inventory_name") or "").strip()
    article_id = str(preview.get("household_article_id") or "").strip()
    if not product_type_id or not inventory_name or not article_id:
        raise ValueError("validated Producttype selection is incomplete")

    ensure_product_inventory_group_schema()
    timestamp = _now()
    with engine.begin() as conn:
        _ensure_product_identity_schema(conn)

        existing_identity = conn.execute(text("""
            SELECT id, global_product_id
            FROM product_identities
            WHERE household_article_id = :household_article_id
              AND COALESCE(is_primary, 1) = 1
              AND COALESCE(active, 1) = 1
            ORDER BY COALESCE(updated_at, created_at, '') DESC
            LIMIT 1
        """), {"household_article_id": article_id}).mappings().first()

        if existing_identity and str(existing_identity.get("global_product_id") or "").strip():
            global_product_id = str(existing_identity.get("global_product_id"))
            identity_created = False
        else:
            global_product_id = get_or_create_global_product(
                conn,
                gtin=None,
                name=inventory_name,
                source="manual_gpc_product_type_confirmation",
            )
            identity_id = str(existing_identity.get("id")) if existing_identity else str(uuid.uuid4())
            if existing_identity:
                conn.execute(text("""
                    UPDATE product_identities
                    SET household_id = :household_id,
                        global_product_id = :global_product_id,
                        identity_type = :identity_type,
                        source = :source,
                        is_primary = 1,
                        confirmed_by_user = 1,
                        active = 1,
                        updated_at = :updated_at
                    WHERE id = :id
                """), {
                    "id": identity_id,
                    "household_id": str(household_id),
                    "global_product_id": global_product_id,
                    "identity_type": "manual_product_type",
                    "source": "manual_gpc_product_type_confirmation",
                    "updated_at": timestamp,
                })
            else:
                conn.execute(text("""
                    INSERT INTO product_identities (
                        id, household_id, household_article_id, global_product_id,
                        identity_type, source, is_primary, confirmed_by_user,
                        active, created_at, updated_at
                    ) VALUES (
                        :id, :household_id, :household_article_id, :global_product_id,
                        :identity_type, :source, 1, 1, 1, :created_at, :updated_at
                    )
                """), {
                    "id": identity_id,
                    "household_id": str(household_id),
                    "household_article_id": article_id,
                    "global_product_id": global_product_id,
                    "identity_type": "manual_product_type",
                    "source": "manual_gpc_product_type_confirmation",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                })
            identity_created = True

        link_result = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=product_type_id,
            comparison_group_key=product_type_id,
            confidence=1.0,
            source="manual_gpc_product_type_confirmation",
            confirmed_by_user=True,
        )
        if not bool(link_result.get("ok")):
            raise ValueError(str(link_result.get("error") or "Producttype link could not be stored"))

    return {
        "household_id": str(household_id),
        "household_article_id": article_id,
        "global_product_id": global_product_id,
        "basis": "manual_gpc_selection_confirmation",
        "confirmation_status": "confirmed",
        "confirmed_by_user": True,
        "identity_created": identity_created,
        "product_type_link_created": True,
        "selected_product_type": selected,
        "mutates_inventory": False,
        "creates_inventory_event": False,
        "mutates_purchase_list": False,
    }
