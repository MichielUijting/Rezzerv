from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_product_candidate_store import (
    build_candidate_context_key,
    build_preview_import_line_fallback,
    ensure_external_product_candidates_schema,
    now_iso,
    _find_existing_candidate,
    _is_protected,
    _serialize_score_breakdown,
)
from app.services.open_food_facts_search_preview import search_open_food_facts_preview


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_text(item) for item in value if _text(item))
    return str(value or "").strip()


def _is_valid_gtin(value: Any) -> bool:
    normalized = _text(value)
    return bool(normalized.isdigit() and len(normalized) in {8, 12, 13, 14})


def _payload_has_known_gtin(payload: dict[str, Any]) -> bool:
    return any(
        _is_valid_gtin(payload.get(field))
        for field in ("gtin", "ean", "barcode", "retailer_article_number", "article_number")
    )


def _off_candidate_from_result(result: dict[str, Any]) -> dict[str, Any]:
    code = _text(
        result.get("candidate_source_product_code")
        or result.get("source_product_code")
        or result.get("gtin")
        or result.get("ean")
        or result.get("barcode")
        or result.get("code")
    )
    return {
        "candidate_name": _text(result.get("candidate_name") or result.get("product_name")),
        "candidate_brand": _text(result.get("candidate_brand") or result.get("brands")),
        "candidate_source_name": "Open Food Facts",
        "candidate_source_product_code": code,
        "source_name": "Open Food Facts",
        "source_product_code": code,
        "retailer_article_number": code,
        "quantity_label": _text(result.get("quantity_label") or result.get("quantity")),
        "variant": _text(result.get("variant") or result.get("quantity") or "OFF"),
        "source_url": _text(result.get("source_url")),
        "score": float(result.get("score") or 0),
        "score_breakdown": result.get("score_breakdown") or {},
        "candidate_status": "candidate",
        "is_probable": bool(float(result.get("score") or 0) >= 0.70),
        "created_by": "open_food_facts_search_preview_save_v1",
    }


def save_open_food_facts_preview_candidates(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist OFF preview results as selectable external candidates.

    This creates external candidate rows only. It does not create global products,
    household articles or inventory events. A separate explicit user action is still
    required to link/promote a candidate. Rows that already carry a valid GTIN/EAN
    are skipped because the external identity is already known.
    """
    ensure_external_product_candidates_schema()

    receipt_line_text = _text(payload.get("receipt_line_text") or payload.get("query"))
    if not receipt_line_text:
        return {
            "ok": False,
            "error": "receipt_line_text is verplicht",
            "saved_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    retailer_code = _text(payload.get("retailer_code")).lower()
    receipt_line_id = _text(payload.get("receipt_line_id")) or None
    purchase_import_line_id = _text(payload.get("purchase_import_line_id")) or None
    context_key = build_candidate_context_key(
        retailer_code,
        receipt_line_text,
        receipt_line_id=receipt_line_id,
        purchase_import_line_id=purchase_import_line_id,
    )

    if _payload_has_known_gtin(payload):
        return {
            "ok": True,
            "preview": {
                "ok": True,
                "status": "skipped_known_gtin",
                "provider": "known_gtin_guardrail",
                "result_count": 0,
                "creates_global_product": False,
                "creates_household_article": False,
                "creates_inventory_event": False,
            },
            "source_name": "open_food_facts",
            "context_key": context_key,
            "retailer_code": retailer_code,
            "receipt_line_text": receipt_line_text,
            "candidate_count": 0,
            "saved_count": 0,
            "updated_count": 0,
            "skipped_count": 1,
            "skipped": [{"reason": "known_gtin_present"}],
            "candidates": [],
            "requires_user_selection": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    storage_purchase_import_line_id = purchase_import_line_id or build_preview_import_line_fallback(context_key)

    preview = search_open_food_facts_preview(payload)
    if not bool(preview.get("ok", True)):
        return {
            "ok": False,
            "error": preview.get("error") or "OFF search-preview kon niet worden uitgevoerd",
            "preview": preview,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }

    candidates = [_off_candidate_from_result(result) for result in list(preview.get("results") or []) if isinstance(result, dict)]
    timestamp = now_iso()
    saved: list[str] = []
    updated: list[str] = []
    skipped: list[dict[str, Any]] = []
    saved_rows: list[dict[str, Any]] = []

    with engine.begin() as conn:
        for candidate in candidates:
            if not candidate.get("candidate_name") or not candidate.get("candidate_source_product_code"):
                skipped.append({"reason": "missing_identity", "candidate_name": candidate.get("candidate_name")})
                continue

            existing = _find_existing_candidate(conn, context_key, retailer_code, candidate)
            if _is_protected(existing):
                skipped.append({"id": existing.get("id"), "reason": "protected_candidate"})
                continue

            candidate_id = str(existing.get("id")) if existing else str(uuid.uuid4())
            params = {
                "id": candidate_id,
                "receipt_line_id": receipt_line_id,
                "purchase_import_line_id": storage_purchase_import_line_id,
                "context_key": context_key,
                "retailer_code": retailer_code,
                "receipt_line_text": receipt_line_text,
                "candidate_name": _text(candidate.get("candidate_name")),
                "candidate_brand": _text(candidate.get("candidate_brand")) or None,
                "candidate_source_name": _text(candidate.get("candidate_source_name")),
                "candidate_source_product_code": _text(candidate.get("candidate_source_product_code")),
                "source_name": _text(candidate.get("source_name")),
                "source_product_code": _text(candidate.get("source_product_code")),
                "retailer_article_number": _text(candidate.get("retailer_article_number")) or None,
                "quantity_label": _text(candidate.get("quantity_label")) or None,
                "variant": _text(candidate.get("variant")) or None,
                "source_url": _text(candidate.get("source_url")) or None,
                "score": float(candidate.get("score") or 0),
                "score_breakdown_json": _serialize_score_breakdown(candidate),
                "candidate_status": _text(candidate.get("candidate_status")) or "candidate",
                "is_probable": 1 if bool(candidate.get("is_probable")) else 0,
                "is_user_confirmed": 0,
                "is_external_database_override": 0,
                "created_by": _text(candidate.get("created_by")) or "open_food_facts_search_preview_save_v1",
                "created_at": timestamp,
                "updated_at": timestamp,
            }

            if existing:
                conn.execute(
                    text(
                        """
                        UPDATE external_product_candidates
                        SET receipt_line_id = :receipt_line_id,
                            purchase_import_line_id = :purchase_import_line_id,
                            receipt_line_text = :receipt_line_text,
                            candidate_brand = :candidate_brand,
                            candidate_source_name = :candidate_source_name,
                            candidate_source_product_code = :candidate_source_product_code,
                            source_name = :source_name,
                            source_product_code = :source_product_code,
                            retailer_article_number = :retailer_article_number,
                            quantity_label = :quantity_label,
                            variant = :variant,
                            source_url = :source_url,
                            score = :score,
                            score_breakdown_json = :score_breakdown_json,
                            candidate_status = :candidate_status,
                            is_probable = :is_probable,
                            updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    params,
                )
                updated.append(candidate_id)
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO external_product_candidates (
                            id, receipt_line_id, purchase_import_line_id, context_key,
                            retailer_code, receipt_line_text, candidate_name, candidate_brand,
                            candidate_source_name, candidate_source_product_code, source_name,
                            source_product_code, retailer_article_number, quantity_label,
                            variant, source_url, score, score_breakdown_json,
                            candidate_status, is_probable, is_user_confirmed,
                            is_external_database_override, created_by, created_at, updated_at
                        ) VALUES (
                            :id, :receipt_line_id, :purchase_import_line_id, :context_key,
                            :retailer_code, :receipt_line_text, :candidate_name, :candidate_brand,
                            :candidate_source_name, :candidate_source_product_code, :source_name,
                            :source_product_code, :retailer_article_number, :quantity_label,
                            :variant, :source_url, :score, :score_breakdown_json,
                            :candidate_status, :is_probable, :is_user_confirmed,
                            :is_external_database_override, :created_by, :created_at, :updated_at
                        )
                        """
                    ),
                    params,
                )
                saved.append(candidate_id)

            saved_rows.append({**params, "id": candidate_id})

    return {
        "ok": True,
        "preview": preview,
        "source_name": "open_food_facts",
        "context_key": context_key,
        "retailer_code": retailer_code,
        "receipt_line_text": receipt_line_text,
        "candidate_count": len(candidates),
        "saved_count": len(saved),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
        "saved_candidate_ids": saved,
        "updated_candidate_ids": updated,
        "skipped": skipped,
        "candidates": saved_rows,
        "requires_user_selection": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
