from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException
from sqlalchemy import inspect, text

from app.db import engine
from app.api.authorization_membership_routes import _actor_context, _require
from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    ensure_direct_location,
    get_default_inventory_handling,
    get_default_inventory_handling_batch,
    record_direct_consumption,
    set_default_inventory_handling,
)

router = APIRouter(tags=["unpacking-day-articles"])

_LINE_OVERRIDE_COLUMNS = {
    "purchase_import_line_id",
    "household_id",
    "inventory_handling",
    "updated_by_user_id",
    "updated_at",
}


def _validate_line_override_table(conn) -> None:
    inspector = inspect(conn)
    table_name = "purchase_import_line_inventory_handling_overrides"
    if not inspector.has_table(table_name):
        raise RuntimeError(
            f"Canonical {table_name} ontbreekt. Voer Alembic migrations uit."
        )
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(table_name)
    }
    missing = _LINE_OVERRIDE_COLUMNS - columns
    if missing:
        raise RuntimeError(
            f"Canonical {table_name} mist kolommen: {sorted(missing)}. "
            "Voer Alembic migrations uit."
        )


def _line_household_id(conn, line_id: str) -> str | None:
    value = conn.execute(text("""
        SELECT b.household_id
        FROM purchase_import_lines l
        JOIN purchase_import_batches b ON b.id = l.batch_id
        WHERE l.id = :line_id
    """), {"line_id": line_id}).scalar()
    return str(value) if value is not None else None


def _normalize_override(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().upper()
    if normalized not in {STOCK, DIRECT_CONSUMPTION}:
        raise ValueError("inventory_handling_override moet STOCK, DIRECT_CONSUMPTION of leeg zijn")
    return normalized


@router.get("/api/households/{household_id}/articles/{household_article_id}/inventory-handling")
def get_article_inventory_handling(
    household_id: str,
    household_article_id: str,
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "articles.view")
        try:
            return get_default_inventory_handling(conn, household_id, household_article_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/households/{household_id}/articles/inventory-handling/batch")
def get_article_inventory_handling_batch_route(
    household_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    article_ids = payload.get("household_article_ids") or []
    if not isinstance(article_ids, list):
        raise HTTPException(status_code=400, detail="household_article_ids moet een lijst zijn")
    if len(article_ids) > 250:
        raise HTTPException(status_code=400, detail="Maximaal 250 huishoudartikelen per aanvraag")

    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "articles.view")
        items = get_default_inventory_handling_batch(conn, household_id, article_ids)
        direct_location = ensure_direct_location(conn, household_id)
        conn.execute(text("UPDATE spaces SET active = TRUE WHERE id = :id"), {"id": direct_location["space_id"]})
        conn.execute(text("UPDATE sublocations SET active = TRUE WHERE id = :id"), {"id": direct_location["sublocation_id"]})
        return {
            "household_id": str(household_id),
            "items": items,
            "direct_location": direct_location,
        }


@router.post("/api/households/{household_id}/purchase-import-lines/inventory-handling-overrides/batch")
def get_line_inventory_handling_overrides_batch(
    household_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    line_ids = payload.get("purchase_import_line_ids") or []
    if not isinstance(line_ids, list):
        raise HTTPException(status_code=400, detail="purchase_import_line_ids moet een lijst zijn")
    normalized_ids = list(dict.fromkeys(str(value).strip() for value in line_ids if str(value).strip()))
    if len(normalized_ids) > 250:
        raise HTTPException(status_code=400, detail="Maximaal 250 bonregels per aanvraag")

    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "unpacking.process")
        _validate_line_override_table(conn)
        items: list[dict[str, Any]] = []
        for line_id in normalized_ids:
            line_household_id = _line_household_id(conn, line_id)
            if line_household_id != str(household_id):
                continue
            override = conn.execute(text("""
                SELECT inventory_handling
                FROM purchase_import_line_inventory_handling_overrides
                WHERE purchase_import_line_id = :line_id
                  AND household_id = :household_id
            """), {"line_id": line_id, "household_id": household_id}).scalar()
            items.append({
                "purchase_import_line_id": line_id,
                "inventory_handling_override": str(override) if override else None,
            })
        return {"household_id": str(household_id), "items": items}


@router.put("/api/households/{household_id}/purchase-import-lines/{line_id}/inventory-handling-override")
def update_line_inventory_handling_override(
    household_id: str,
    line_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    try:
        override = _normalize_override(payload.get("inventory_handling_override"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "unpacking.process")
        line_household_id = _line_household_id(conn, line_id)
        if line_household_id is None:
            raise HTTPException(status_code=404, detail="Bonregel niet gevonden")
        if line_household_id != str(household_id):
            raise HTTPException(status_code=404, detail="Bonregel niet gevonden")

        _validate_line_override_table(conn)
        if override is None:
            conn.execute(text("""
                DELETE FROM purchase_import_line_inventory_handling_overrides
                WHERE purchase_import_line_id = :line_id
                  AND household_id = :household_id
            """), {"line_id": line_id, "household_id": household_id})
        else:
            conn.execute(text("""
                INSERT INTO purchase_import_line_inventory_handling_overrides (
                    purchase_import_line_id,
                    household_id,
                    inventory_handling,
                    updated_by_user_id,
                    updated_at
                ) VALUES (
                    :line_id,
                    :household_id,
                    :inventory_handling,
                    :user_id,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT(purchase_import_line_id) DO UPDATE SET
                    household_id = excluded.household_id,
                    inventory_handling = excluded.inventory_handling,
                    updated_by_user_id = excluded.updated_by_user_id,
                    updated_at = CURRENT_TIMESTAMP
            """), {
                "line_id": line_id,
                "household_id": household_id,
                "inventory_handling": override,
                "user_id": context["user_id"],
            })

        return {
            "purchase_import_line_id": str(line_id),
            "household_id": str(household_id),
            "inventory_handling_override": override,
        }


@router.put("/api/households/{household_id}/articles/{household_article_id}/inventory-handling")
def update_article_inventory_handling(
    household_id: str,
    household_article_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "articles.manage")
        try:
            return set_default_inventory_handling(
                conn,
                household_id=household_id,
                household_article_id=household_article_id,
                handling=str(payload.get("default_inventory_handling") or ""),
                actor_user_id=context["user_id"],
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/households/{household_id}/articles/{household_article_id}/direct-consumption")
def process_direct_consumption(
    household_id: str,
    household_article_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    del authorization
    with engine.begin() as conn:
        context = _actor_context(conn, household_id)
        _require(conn, context, "unpacking.process")
        try:
            result = record_direct_consumption(
                conn,
                household_id=household_id,
                household_article_id=household_article_id,
                quantity=Decimal(str(payload.get("quantity") or "0")),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                actor_user_id=context["user_id"],
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ArithmeticError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if result["handling"] != DIRECT_CONSUMPTION:
            raise HTTPException(status_code=500, detail="Onverwachte voorraadverwerking")
        return result
