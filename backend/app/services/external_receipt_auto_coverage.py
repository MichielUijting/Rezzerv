from __future__ import annotations

import importlib
import logging
import sys
from functools import wraps
from typing import Any, Callable

from sqlalchemy import text

from app.db import engine
from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded
from app.services.external_database_matchflow_evidence import ensure_external_receipt_item_candidates
from app.services.loyalty_stamp_transaction_service import sync_loyalty_stamp_transactions_for_receipt_table

LOGGER = logging.getLogger(__name__)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _receipt_table_exists(conn) -> bool:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'receipt_table_lines'")
        ).first() is not None

    return conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'receipt_table_lines'
            LIMIT 1
            """
        )
    ).first() is not None


def _is_external_matching_allowed(row: dict[str, Any]) -> bool:
    return not is_spaarzegels_flow_excluded(row)


def _receipt_table_items(receipt_table_id: str) -> list[dict[str, Any]]:
    normalized_table_id = _text(receipt_table_id)
    if not normalized_table_id:
        return []

    with engine.begin() as conn:
        if not _receipt_table_exists(conn):
            return []

        rows = conn.execute(
            text(
                """
                SELECT
                    rtl.id AS receipt_line_id,
                    rt.store_name AS retailer_code,
                    COALESCE(NULLIF(rtl.raw_label, ''), rtl.normalized_label) AS receipt_line_text,
                    rtl.raw_label AS raw_label,
                    rtl.normalized_label AS normalized_label,
                    rtl.barcode AS retailer_article_number,
                    TRIM(COALESCE(CAST(rtl.quantity AS TEXT), '') || ' ' || COALESCE(CAST(rtl.unit AS TEXT), '')) AS quantity_label,
                    rtl.unit_price AS unit_price,
                    rtl.line_total AS line_total,
                    rtl.line_total AS price
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                WHERE rtl.receipt_table_id = :receipt_table_id
                ORDER BY rtl.line_index ASC, rtl.id ASC
                """
            ),
            {"receipt_table_id": normalized_table_id},
        ).mappings().all()

    items: list[dict[str, Any]] = []
    for row in rows:
        row_data = dict(row)
        receipt_text = _text(row_data.get("receipt_line_text")) or _text(row_data.get("normalized_label"))
        if not receipt_text:
            continue
        if not _is_external_matching_allowed(row_data):
            continue
        items.append({
            "receipt_line_id": _text(row_data.get("receipt_line_id")),
            "receipt_line_text": receipt_text,
            "retailer_code": _text(row_data.get("retailer_code")),
            "retailer_article_number": _text(row_data.get("retailer_article_number")),
            "quantity_label": _text(row_data.get("quantity_label")),
            "price": row_data.get("price"),
        })

    return items


def _sync_stamp_transactions(receipt_table_id: str) -> dict[str, Any]:
    with engine.begin() as conn:
        return sync_loyalty_stamp_transactions_for_receipt_table(conn, receipt_table_id)


def auto_ensure_external_candidates_for_receipt_table(
    receipt_table_id: str,
    include_below_threshold: bool = True,
) -> dict[str, Any]:
    """Lees echte externe kandidaten bij voor alle productregels van een nieuw opgeslagen bon.

    Dit is productgedrag, geen PO-rapport. De functie mag uitsluitend kandidaatcache
    vullen in `external_product_candidates`. Ze maakt geen Mijn artikel, geen
    global product en geen voorraadmutatie. Spaarzegels blijven financiële
    bonregels voor de kassasom, maar worden niet naar productmatching gestuurd.
    """
    items = _receipt_table_items(receipt_table_id)
    if not items:
        return {
            "ok": True,
            "receipt_table_id": _text(receipt_table_id),
            "trigger": "receipt_table_saved",
            "item_count": 0,
            "processed": 0,
            "saved_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "errors": [],
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    result = ensure_external_receipt_item_candidates(
        items=items,
        include_below_threshold=include_below_threshold,
    )

    return {
        "ok": bool(result.get("ok", True)),
        "receipt_table_id": _text(receipt_table_id),
        "trigger": "receipt_table_saved",
        "item_count": len(items),
        "processed": int(result.get("processed") or 0),
        "saved_count": int(result.get("saved_count") or 0),
        "updated_count": int(result.get("updated_count") or 0),
        "skipped_count": int(result.get("skipped_count") or 0),
        "errors": list(result.get("errors") or []),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def _with_receipt_auto_coverage(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if not isinstance(result, dict):
            return result

        next_result = dict(result)
        receipt_table_id = _text(next_result.get("receipt_table_id"))
        if not receipt_table_id or bool(next_result.get("duplicate")):
            return next_result

        try:
            next_result["loyalty_stamp_transactions"] = _sync_stamp_transactions(receipt_table_id)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Spaarzegeltransacties synchroniseren mislukt voor bon %s: %s", receipt_table_id, exc)
            next_result["loyalty_stamp_transactions"] = {"ok": False, "receipt_table_id": receipt_table_id, "error": str(exc)}

        try:
            next_result["external_candidate_coverage"] = auto_ensure_external_candidates_for_receipt_table(
                receipt_table_id,
                include_below_threshold=True,
            )
        except Exception as exc:  # pragma: no cover - upload mag niet falen door kandidaatcache
            LOGGER.warning(
                "Automatische externe kandidaatdekking mislukt voor bon %s: %s",
                receipt_table_id,
                exc,
            )
            next_result["external_candidate_coverage"] = {
                "ok": False,
                "receipt_table_id": receipt_table_id,
                "trigger": "receipt_table_saved",
                "error": str(exc),
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        return next_result

    return wrapped


def _with_reparse_auto_coverage(original: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if not isinstance(result, dict):
            return result

        next_result = dict(result)
        receipt_table_id = _text(next_result.get("receipt_table_id"))
        if not receipt_table_id:
            if len(args) >= 3:
                receipt_table_id = _text(args[2])
            else:
                receipt_table_id = _text(kwargs.get("receipt_table_id"))
        if not receipt_table_id:
            return next_result

        try:
            next_result["loyalty_stamp_transactions"] = _sync_stamp_transactions(receipt_table_id)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Spaarzegeltransacties synchroniseren na heranalyse mislukt voor bon %s: %s", receipt_table_id, exc)
            next_result["loyalty_stamp_transactions"] = {"ok": False, "receipt_table_id": receipt_table_id, "error": str(exc)}

        try:
            next_result["external_candidate_coverage"] = auto_ensure_external_candidates_for_receipt_table(
                receipt_table_id,
                include_below_threshold=True,
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.warning(
                "Automatische externe kandidaatdekking na heranalyse mislukt voor bon %s: %s",
                receipt_table_id,
                exc,
            )
            next_result["external_candidate_coverage"] = {
                "ok": False,
                "receipt_table_id": receipt_table_id,
                "trigger": "receipt_table_reparsed",
                "error": str(exc),
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            }

        return next_result

    return wrapped


def _patch_module_function(module: Any, function_name: str, wrapper_factory: Callable[[Callable[..., Any]], Callable[..., Any]]) -> bool:
    original = getattr(module, function_name, None)
    if not callable(original):
        return False
    marker_name = f"_m2c2i24s_original_{function_name}"
    if hasattr(module, marker_name):
        return False
    setattr(module, marker_name, original)
    setattr(module, function_name, wrapper_factory(original))
    return True


def install_receipt_auto_candidate_coverage() -> dict[str, Any]:
    """Installeer runtime hooks voor nieuwe bonnen.

    FastAPI importeert `ingest_receipt` en `reparse_receipt` ook rechtstreeks in
    `app.main`. Daarom patchen we zowel de service-module als, als die al geladen
    is, de globale namen in `app.main`.
    """
    patched: list[str] = []

    receipt_service = importlib.import_module("app.services.receipt_service")
    if _patch_module_function(receipt_service, "ingest_receipt", _with_receipt_auto_coverage):
        patched.append("app.services.receipt_service.ingest_receipt")
    if _patch_module_function(receipt_service, "reparse_receipt", _with_reparse_auto_coverage):
        patched.append("app.services.receipt_service.reparse_receipt")

    main_module = sys.modules.get("app.main")
    if main_module is not None:
        if _patch_module_function(main_module, "ingest_receipt", _with_receipt_auto_coverage):
            patched.append("app.main.ingest_receipt")
        if _patch_module_function(main_module, "reparse_receipt", _with_reparse_auto_coverage):
            patched.append("app.main.reparse_receipt")

    return {
        "ok": True,
        "patched": patched,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
