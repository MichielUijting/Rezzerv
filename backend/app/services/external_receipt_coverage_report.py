from __future__ import annotations

from typing import Any

from app.services.external_candidate_diagnostics import diagnose_real_candidate_coverage
from app.services.external_product_candidate_store import list_external_receipt_items
from app.services.external_database_matchers import normalize_match_text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _context_key(item: dict[str, Any]) -> str:
    return _text(item.get("context_key")) or _text(item.get("id"))


def _retailer_code(item: dict[str, Any]) -> str:
    return normalize_match_text(
        _text(item.get("retailer_code"))
        or _text(item.get("retailerCode"))
        or "onbekend"
    )


def _receipt_line_text(item: dict[str, Any]) -> str:
    return _text(item.get("receipt_line_text")) or _text(item.get("receiptLineText"))


def _receipt_line_id(item: dict[str, Any]) -> str:
    return _text(item.get("receipt_line_id"))


def _purchase_import_line_id(item: dict[str, Any]) -> str:
    return _text(item.get("purchase_import_line_id"))


def _best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    return sorted(candidates, key=lambda candidate: float(candidate.get("score") or 0), reverse=True)[0]


def _build_blind_item_set(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Maak een unieke, bonartikelgedreven set zonder vooraf bekende artikellijst.

    De input komt uit de bestaande receipt-items flow. Die kan placeholders en eerder
    opgeslagen kandidaten bevatten. Voor de blind coverage-scan telt elke unieke
    bonartikelcontext één keer.
    """
    grouped: dict[str, dict[str, Any]] = {}

    for item in raw_items:
        receipt_text = _receipt_line_text(item)
        if not receipt_text:
            continue

        retailer = _retailer_code(item)
        context_key = _context_key(item) or f"blind:{retailer}:{normalize_match_text(receipt_text)}"
        current = grouped.get(context_key)

        next_item = {
            "context_key": context_key,
            "receipt_line_id": _receipt_line_id(item),
            "purchase_import_line_id": _purchase_import_line_id(item),
            "retailer_code": retailer,
            "receipt_line_text": receipt_text,
        }

        if current is None:
            grouped[context_key] = next_item
            continue

        # Verrijk lege IDs als een latere rij meer context heeft.
        if not current.get("receipt_line_id") and next_item.get("receipt_line_id"):
            current["receipt_line_id"] = next_item["receipt_line_id"]
        if not current.get("purchase_import_line_id") and next_item.get("purchase_import_line_id"):
            current["purchase_import_line_id"] = next_item["purchase_import_line_id"]
        if current.get("retailer_code") in {"", "onbekend"} and next_item.get("retailer_code"):
            current["retailer_code"] = next_item["retailer_code"]

    return list(grouped.values())


def build_blind_receipt_coverage_report(
    limit: int = 500,
    include_below_threshold: bool = True,
) -> dict[str, Any]:
    """Valideer blind alle actuele bonartikelen tegen de echte herkenningsstraat.

    Deze functie gebruikt geen vooraf bekende artikellijst en schrijft geen
    kandidaten, Mijn-artikelen, global products of voorraadmutaties. De uitkomst
    is bedoeld als PO-rapport: elk bonartikel krijgt óf echte kandidaten óf een
    veilige geen-match verklaring.
    """
    normalized_limit = max(1, min(int(limit or 500), 500))
    receipt_items_response = list_external_receipt_items(limit=normalized_limit)
    raw_items = list(receipt_items_response.get("items") or [])
    blind_items = _build_blind_item_set(raw_items)

    results: list[dict[str, Any]] = []
    total_candidates = 0
    total_real_candidates = 0
    total_forbidden_candidates = 0
    total_coverage_fallback = 0
    total_legacy_fallback = 0

    for item in blind_items:
        diagnosis = diagnose_real_candidate_coverage(
            retailer_code=item["retailer_code"],
            receipt_line_text=item["receipt_line_text"],
            include_below_threshold=include_below_threshold,
        )
        candidates = list(diagnosis.get("candidates") or [])
        best_candidate = _best_candidate(candidates)
        candidate_count = int(diagnosis.get("candidate_count") or 0)
        real_candidate_count = int(diagnosis.get("real_candidate_count") or 0)
        forbidden_candidate_count = int(diagnosis.get("forbidden_candidate_count") or 0)
        uses_coverage_fallback = bool(diagnosis.get("uses_coverage_fallback"))
        uses_legacy_fallback = bool(diagnosis.get("uses_legacy_fallback"))

        total_candidates += candidate_count
        total_real_candidates += real_candidate_count
        total_forbidden_candidates += forbidden_candidate_count
        if uses_coverage_fallback:
            total_coverage_fallback += 1
        if uses_legacy_fallback:
            total_legacy_fallback += 1

        results.append({
            "context_key": item["context_key"],
            "receipt_line_id": item.get("receipt_line_id") or "",
            "purchase_import_line_id": item.get("purchase_import_line_id") or "",
            "retailer_code": diagnosis.get("retailer_code"),
            "receipt_line_text": item["receipt_line_text"],
            "normalized_receipt_line_text": diagnosis.get("normalized_receipt_line_text"),
            "candidate_count": candidate_count,
            "real_candidate_count": real_candidate_count,
            "forbidden_candidate_count": forbidden_candidate_count,
            "has_real_candidate": bool(diagnosis.get("has_real_candidate")),
            "has_forbidden_fallback_candidate": bool(diagnosis.get("has_forbidden_fallback_candidate")),
            "uses_coverage_fallback": uses_coverage_fallback,
            "uses_legacy_fallback": uses_legacy_fallback,
            "candidate_source": diagnosis.get("candidate_source"),
            "no_candidate_reason": diagnosis.get("no_candidate_reason"),
            "diagnostic_reasons": list(diagnosis.get("diagnostic_reasons") or []),
            "receipt_analysis": diagnosis.get("receipt_analysis") or {},
            "best_candidate": {
                "candidate_name": _text(best_candidate.get("candidate_name")) if best_candidate else "",
                "candidate_brand": _text(best_candidate.get("candidate_brand")) if best_candidate else "",
                "candidate_source_name": _text(best_candidate.get("candidate_source_name") or best_candidate.get("source_name")) if best_candidate else "",
                "candidate_source_product_code": _text(best_candidate.get("candidate_source_product_code") or best_candidate.get("source_product_code")) if best_candidate else "",
                "retailer_article_number": _text(best_candidate.get("retailer_article_number")) if best_candidate else "",
                "score": best_candidate.get("score") if best_candidate else None,
                "candidate_status": _text(best_candidate.get("candidate_status") or best_candidate.get("status")) if best_candidate else "",
            },
        })

    items_with_real_candidate = sum(1 for item in results if item["has_real_candidate"])
    items_without_real_candidate = len(results) - items_with_real_candidate
    items_with_forbidden_fallback = sum(1 for item in results if item["has_forbidden_fallback_candidate"])

    return {
        "ok": True,
        "mode": "blind_receipt_item_coverage",
        "source": "current_receipt_items",
        "limit": normalized_limit,
        "include_below_threshold": bool(include_below_threshold),
        "total_items": len(results),
        "items_with_real_candidate": items_with_real_candidate,
        "items_without_real_candidate": items_without_real_candidate,
        "items_with_forbidden_fallback": items_with_forbidden_fallback,
        "candidate_count": total_candidates,
        "real_candidate_count": total_real_candidates,
        "forbidden_candidate_count": total_forbidden_candidates,
        "coverage_fallback_item_count": total_coverage_fallback,
        "legacy_fallback_item_count": total_legacy_fallback,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "writes_database": False,
        "items": results,
    }
