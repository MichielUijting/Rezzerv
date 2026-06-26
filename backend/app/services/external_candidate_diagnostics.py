from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_database_matchers import match_retailer_receipt_line, normalize_match_text
from app.services.external_product_index_store import search_external_product_index_candidates
from app.services.receipt_product_intent_analyzer import analyze_receipt_product_line

FORBIDDEN_FALLBACK_SOURCES = {
    "receipt_product_intent_fallback",
    "receipt_unresolved_fallback",
    "learned_receipt_line",
}

FORBIDDEN_FALLBACK_STATUSES = {
    "fallback_candidate",
    "unresolved_candidate",
    "concept_candidate",
}


def _table_exists(conn, table_name: str) -> bool:
    dialect_name = str(engine.dialect.name or "").lower()
    if dialect_name == "sqlite":
        return conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table' AND name = :table_name"),
            {"table_name": table_name},
        ).first() is not None

    return conn.execute(
        text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :table_name
            LIMIT 1
        """),
        {"table_name": table_name},
    ).first() is not None


def _count_table(conn, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    row = conn.execute(text(f"SELECT COUNT(*) AS count FROM {table_name}")).mappings().first()
    return int(row.get("count") or 0) if row else 0


def _count_forbidden_candidates(conn) -> int:
    if not _table_exists(conn, "external_product_candidates"):
        return 0
    row = conn.execute(text("""
        SELECT COUNT(*) AS count
        FROM external_product_candidates
        WHERE candidate_source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR source_name IN ('receipt_product_intent_fallback', 'receipt_unresolved_fallback', 'learned_receipt_line')
           OR candidate_status IN ('fallback_candidate', 'unresolved_candidate', 'concept_candidate')
           OR candidate_source_product_code LIKE 'fallback:%'
           OR source_product_code LIKE 'fallback:%'
    """)).mappings().first()
    return int(row.get("count") or 0) if row else 0


def _count_forbidden_index_rows(conn) -> int:
    if not _table_exists(conn, "external_product_index"):
        return 0
    row = conn.execute(text("""
        SELECT COUNT(*) AS count
        FROM external_product_index
        WHERE source_name = 'learned_receipt_line'
           OR source_product_code LIKE 'learned:%'
           OR code LIKE 'learned:%'
    """)).mappings().first()
    return int(row.get("count") or 0) if row else 0


def _candidate_is_forbidden(candidate: dict[str, Any]) -> bool:
    source_names = {
        str(candidate.get("candidate_source_name") or "").strip(),
        str(candidate.get("source_name") or "").strip(),
    }
    statuses = {
        str(candidate.get("candidate_status") or "").strip(),
        str(candidate.get("status") or "").strip(),
    }
    source_code = str(candidate.get("candidate_source_product_code") or candidate.get("source_product_code") or "").strip()
    return bool(
        source_names & FORBIDDEN_FALLBACK_SOURCES
        or statuses & FORBIDDEN_FALLBACK_STATUSES
        or source_code.startswith("fallback:")
        or source_code.startswith("learned:")
    )


def diagnose_real_candidate_coverage(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    """Diagnoseer echte kandidaatdekking zonder fallback te maken.

    Deze functie schrijft niets. Ze verklaart waarom een bonregel wel of geen echte
    kandidaat heeft en markeert expliciet of verboden fallbackdata aanwezig is.
    """
    normalized_retailer = normalize_match_text(retailer_code)
    normalized_receipt = normalize_match_text(receipt_line_text)
    analysis = analyze_receipt_product_line(receipt_line_text, retailer_code=normalized_retailer)
    index_rows = search_external_product_index_candidates(
        receipt_line_text,
        retailer_code=normalized_retailer,
        limit=10,
        additional_search_terms=list(getattr(analysis, "variant_terms", []) or []),
    )
    match = match_retailer_receipt_line(
        retailer_code=normalized_retailer,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )
    candidates = list(match.get("candidates") or [])
    forbidden_in_result = [candidate for candidate in candidates if _candidate_is_forbidden(candidate)]

    real_candidates = [candidate for candidate in candidates if not _candidate_is_forbidden(candidate)]

    with engine.begin() as conn:
        index_row_count = _count_table(conn, "external_product_index")
        saved_candidate_count = _count_table(conn, "external_product_candidates")
        forbidden_saved_candidate_count = _count_forbidden_candidates(conn)
        forbidden_index_row_count = _count_forbidden_index_rows(conn)

    reasons: list[str] = []
    if not normalized_receipt:
        reasons.append("empty_receipt_line")
    if index_row_count == 0:
        reasons.append("external_product_index_empty")
    if not index_rows:
        reasons.append("no_index_rows_for_search_terms")
    if not real_candidates:
        reasons.append("no_real_candidate_after_scoring")
    if forbidden_in_result:
        reasons.append("forbidden_fallback_candidate_returned")

    return {
        "ok": True,
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "normalized_receipt_line_text": normalized_receipt,
        "candidate_count": len(candidates),
        "real_candidate_count": len(real_candidates),
        "forbidden_candidate_count": len(forbidden_in_result),
        "has_real_candidate": bool(real_candidates),
        "has_forbidden_fallback_candidate": bool(forbidden_in_result),
        "candidate_source": match.get("candidate_source"),
        "uses_coverage_fallback": bool(match.get("uses_coverage_fallback")),
        "uses_legacy_fallback": bool(match.get("uses_legacy_fallback")),
        "no_candidate_reason": match.get("no_candidate_reason"),
        "diagnostic_reasons": reasons,
        "index_probe": {
            "external_product_index_rows": index_row_count,
            "search_probe_rows": len(index_rows),
            "sample_sources": sorted({str(row.get("source_name") or "") for row in index_rows if str(row.get("source_name") or "").strip()})[:10],
        },
        "saved_candidate_probe": {
            "external_product_candidates_rows": saved_candidate_count,
            "forbidden_saved_candidate_rows": forbidden_saved_candidate_count,
            "forbidden_index_rows": forbidden_index_row_count,
        },
        "receipt_analysis": {
            "product_intent": getattr(analysis, "product_intent", ""),
            "product_type": getattr(analysis, "product_type", ""),
            "category": getattr(analysis, "category", ""),
            "quantity_label": getattr(analysis, "quantity_label", ""),
            "variant_terms": list(getattr(analysis, "variant_terms", []) or []),
            "retailer_catalog_matched": bool((getattr(analysis, "retailer_catalog_match", {}) or {}).get("matched")),
        },
        "candidates": real_candidates[:5],
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "writes_database": False,
    }
