"""Read-only bonartikelprojectie en expliciet herstel van cataloguskoppelingen.

De leesfuncties in dit bestand voeren uitsluitend SELECT-query's en projectie in
geheugen uit. Eventuele historische reparatie van bevestigde kandidaten is een
afzonderlijke, expliciete schrijfactie.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_ui_projection import (
    project_central_link_truth_rows,
)
from app.services.external_product_candidate_store import (
    _m2c2h5_list_purchase_import_placeholders,
    _m2c2i_fix2_apply_status_fields,
    _m2c2i_fix7a3_apply_catalog_status_to_placeholders,
    _m2c2i_fix7a3_normalized_receipt_key,
    _m2c2i_fix7b_dedupe_top_receipt_items,
    _m2c2i_fix7b_ensure_catalog_products_for_article_codes,
    _m2c2l_enrich_linked_receipt_items,
    ensure_external_product_candidates_schema,
)

_MAX_SCAN_LIMIT = 500
_CANDIDATE_DEPENDENT_FIELDS = {
    "bestCandidateName",
    "productType",
    "bestCandidateCode",
    "bestCandidateScore",
    "candidateCount",
}


def _clean(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _contains(value: Any, expected: str) -> bool:
    needle = _clean(expected).lower()
    return not needle or needle in _clean(value).lower()


def _is_linked(item: dict[str, Any]) -> bool:
    return bool(
        item.get("central_link_active") is True
        or item.get("is_linked_to_catalog") is True
        or (
            _clean(item.get("global_product_id"))
            and _clean(item.get("status") or item.get("candidate_status"))
            == "linked_to_catalog"
        )
    )


def _best_candidate(item: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        candidate
        for candidate in item.get("candidates") or []
        if isinstance(candidate, dict)
    ]
    if not candidates:
        return {}

    def priority(candidate: dict[str, Any]) -> tuple[Any, ...]:
        linked = bool(candidate.get("is_linked_to_catalog"))
        score = float(candidate.get("score") or 0)
        return (0 if linked else 1, -score, _clean(candidate.get("candidate_name")))

    return sorted(candidates, key=priority)[0]


def _field_value(item: dict[str, Any], field: str) -> Any:
    candidate = _best_candidate(item)
    values = {
        "receiptLineText": item.get("receipt_line_text"),
        "retailerCode": item.get("retailer_code"),
        "catalogLinked": 1 if _is_linked(item) else 0,
        "quantity": item.get("quantity_label"),
        "price": item.get("price"),
        "bestCandidateName": (
            item.get("linked_candidate_name")
            or candidate.get("candidate_name")
        ),
        "productType": item.get("linked_product_type"),
        "bestCandidateCode": (
            item.get("linked_gtin")
            or item.get("gtin")
            or candidate.get("gtin")
            or candidate.get("ean")
            or candidate.get("candidate_source_product_code")
            or candidate.get("source_product_code")
        ),
        "bestCandidateScore": (
            item.get("linked_score")
            if item.get("linked_score") is not None
            else candidate.get("score")
        ),
        "candidateCount": item.get("candidate_count") or len(item.get("candidates") or []),
    }
    return values.get(field, values["receiptLineText"])


def _matches_filters(item: dict[str, Any], filters: dict[str, str]) -> bool:
    if not _contains(_field_value(item, "receiptLineText"), filters.get("receiptLineText", "")):
        return False
    if not _contains(_field_value(item, "retailerCode"), filters.get("retailerCode", "")):
        return False

    catalog_filter = _clean(filters.get("catalogLinked", "all")).lower()
    if catalog_filter == "linked" and not _is_linked(item):
        return False
    if catalog_filter == "unlinked" and _is_linked(item):
        return False

    for field in (
        "quantity",
        "price",
        "bestCandidateName",
        "productType",
        "bestCandidateCode",
        "bestCandidateScore",
        "candidateCount",
    ):
        if not _contains(_field_value(item, field), filters.get(field, "")):
            return False
    return True


def _sort_items(
    items: list[dict[str, Any]],
    *,
    sort_key: str,
    sort_desc: bool,
) -> list[dict[str, Any]]:
    def sort_value(item: dict[str, Any]) -> tuple[int, Any]:
        value = _field_value(item, sort_key)
        if sort_key in {"price", "bestCandidateScore", "candidateCount", "catalogLinked"}:
            try:
                return (0, float(value))
            except (TypeError, ValueError):
                return (1, 0.0)
        return (0, _clean(value).lower())

    return sorted(items, key=sort_value, reverse=bool(sort_desc))


def _project_rows(conn, placeholders: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projected_placeholders = _m2c2i_fix7a3_apply_catalog_status_to_placeholders(
        placeholders,
        candidates,
    )
    projected_placeholders = _m2c2l_enrich_linked_receipt_items(
        conn,
        projected_placeholders,
    )
    combined = _m2c2i_fix7b_dedupe_top_receipt_items(projected_placeholders)
    enriched = _m2c2i_fix2_apply_status_fields([dict(row) for row in combined])
    centrally_projected = project_central_link_truth_rows(conn, enriched)
    return _m2c2i_fix7b_dedupe_top_receipt_items(centrally_projected)


def _candidate_rows_for_placeholders(conn, placeholders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    purchase_ids = sorted({
        _clean(item.get("purchase_import_line_id"))
        for item in placeholders
        if _clean(item.get("purchase_import_line_id"))
    })
    context_keys = sorted({
        _clean(item.get("context_key"))
        for item in placeholders
        if _clean(item.get("context_key"))
    })
    if not purchase_ids and not context_keys:
        return []

    where_parts: list[str] = []
    params: dict[str, Any] = {}

    if purchase_ids:
        bindings = []
        for index, value in enumerate(purchase_ids):
            key = f"purchase_id_{index}"
            params[key] = value
            bindings.append(f":{key}")
        where_parts.append(f"purchase_import_line_id IN ({', '.join(bindings)})")

    if context_keys:
        bindings = []
        for index, value in enumerate(context_keys):
            key = f"context_key_{index}"
            params[key] = value
            bindings.append(f":{key}")
        where_parts.append(f"context_key IN ({', '.join(bindings)})")

    rows = conn.execute(
        text(
            "SELECT * FROM external_product_candidates "
            f"WHERE {' OR '.join(where_parts)} "
            "ORDER BY updated_at DESC, score DESC"
        ),
        params,
    ).mappings().all()
    return [dict(row) for row in rows]


def list_external_receipt_items_read_only(limit: int = 500) -> dict[str, Any]:
    """Lees het bonartikelenoverzicht zonder databasewijzigingen."""

    normalized_limit = max(1, min(int(limit or 500), _MAX_SCAN_LIMIT))

    with engine.connect() as conn:
        candidate_rows = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                ORDER BY updated_at DESC, score DESC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()

        candidates = [dict(row) for row in candidate_rows]
        existing_context_keys = {
            _clean(row.get("context_key"))
            for row in candidates
            if _clean(row.get("context_key"))
        }
        placeholders = _m2c2h5_list_purchase_import_placeholders(
            conn,
            existing_context_keys,
            normalized_limit,
        )
        items = _project_rows(conn, placeholders, candidates)

    return {
        "items": items[:normalized_limit],
        "candidate_rows": len(candidates),
        "purchase_import_line_rows": len(placeholders),
        "total": len(items[:normalized_limit]),
        "read_only": True,
    }


def list_external_receipt_items_page_read_only(
    *,
    page: int = 1,
    page_size: int = 10,
    sort_key: str = "receiptLineText",
    sort_desc: bool = False,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Geef één serverpagina terug en verrijk alleen zichtbare regels.

    De snelle route scant uitsluitend lichte bonregelmetadata en haalt kandidaten
    pas op nadat de pagina is bepaald. Alleen bij filters of sortering die
    kandidaatdata vereisen wordt teruggevallen op de volledige read-only
    projectie, zodat het resultaat functioneel correct blijft.
    """

    normalized_page = max(1, int(page or 1))
    normalized_page_size = max(1, min(int(page_size or 10), 100))
    normalized_filters = dict(filters or {})
    candidate_filter_active = any(
        _clean(normalized_filters.get(field))
        for field in _CANDIDATE_DEPENDENT_FIELDS
    )
    requires_full_projection = candidate_filter_active or sort_key in _CANDIDATE_DEPENDENT_FIELDS

    if requires_full_projection:
        payload = list_external_receipt_items_read_only(limit=_MAX_SCAN_LIMIT)
        all_items = [dict(item) for item in payload.get("items") or []]
        filtered = [item for item in all_items if _matches_filters(item, normalized_filters)]
        ordered = _sort_items(filtered, sort_key=sort_key, sort_desc=sort_desc)
        total = len(ordered)
        start = (normalized_page - 1) * normalized_page_size
        page_items = ordered[start:start + normalized_page_size]
        return {
            "items": page_items,
            "total": total,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "page_count": max(1, math.ceil(total / normalized_page_size)),
            "read_only": True,
            "projection_mode": "full_for_candidate_filter_or_sort",
        }

    with engine.connect() as conn:
        placeholders = _m2c2h5_list_purchase_import_placeholders(
            conn,
            set(),
            _MAX_SCAN_LIMIT,
        )
        lightweight_items = _m2c2i_fix7b_dedupe_top_receipt_items(placeholders)
        filtered = [
            item
            for item in lightweight_items
            if _matches_filters(item, normalized_filters)
        ]
        ordered = _sort_items(filtered, sort_key=sort_key, sort_desc=sort_desc)
        total = len(ordered)
        start = (normalized_page - 1) * normalized_page_size
        visible_placeholders = ordered[start:start + normalized_page_size]
        visible_candidates = _candidate_rows_for_placeholders(conn, visible_placeholders)
        page_items = _project_rows(conn, visible_placeholders, visible_candidates)
        page_items = _sort_items(page_items, sort_key=sort_key, sort_desc=sort_desc)

    return {
        "items": page_items,
        "total": total,
        "page": normalized_page,
        "page_size": normalized_page_size,
        "page_count": max(1, math.ceil(total / normalized_page_size)),
        "read_only": True,
        "projection_mode": "visible_page_only",
    }


def repair_confirmed_external_catalog_links(limit: int = 500) -> dict[str, Any]:
    """Voer het voormalige impliciete herstel uitsluitend expliciet uit."""

    normalized_limit = max(1, min(int(limit or 500), _MAX_SCAN_LIMIT))
    ensure_external_product_candidates_schema()

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                ORDER BY updated_at DESC, score DESC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()
        candidates = [dict(row) for row in rows]
        repaired = _m2c2i_fix7b_ensure_catalog_products_for_article_codes(
            conn,
            candidates,
        )

    repaired_count = sum(
        1
        for before, after in zip(candidates, repaired)
        if (
            _clean(before.get("global_product_id"))
            != _clean(after.get("global_product_id"))
            or _clean(before.get("status"))
            != _clean(after.get("status"))
            or _clean(before.get("candidate_status"))
            != _clean(after.get("candidate_status"))
        )
    )

    return {
        "ok": True,
        "examined_count": len(candidates),
        "repaired_count": repaired_count,
        "explicit_write_action": True,
        "creates_inventory_event": False,
    }
