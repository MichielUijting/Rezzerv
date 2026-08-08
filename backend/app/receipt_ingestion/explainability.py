"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: none
- Writes Data: none
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

PARSER_QUALITY_LABELS = {
    "approved": "Parser bruikbaar",
    "parsed": "Controle parser nodig",
    "partial": "Controle parser nodig",
    "review_needed": "Controle parser nodig",
    "failed": "Controle parser nodig",
    "duplicate": "Controle parser nodig",
}


def _safe_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _line_total_sum(lines: list[dict[str, Any]]) -> Decimal | None:
    total = Decimal("0")
    seen = False
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        value = _safe_decimal(line.get("line_total"))
        if value is None:
            continue
        total += value
        seen = True
    return total if seen else None


def _discount_sum(lines: list[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        value = _safe_decimal(line.get("discount_amount"))
        if value is not None:
            total += value
    return total


def _status_explanation(result: Any, net_line_sum: Decimal | None, chosen_total: Decimal | None) -> dict[str, Any]:
    parse_status = str(getattr(result, "parse_status", "") or "").strip().lower()
    label = PARSER_QUALITY_LABELS.get(parse_status, "Controle parser nodig")
    reasons: list[str] = []

    if not getattr(result, "is_receipt", False):
        reasons.append("Parser herkende de invoer niet betrouwbaar als kassabon.")
    if not getattr(result, "store_name", None):
        reasons.append("Winkelnaam ontbreekt of is onzeker.")
    if chosen_total is None:
        reasons.append("Totaalbedrag ontbreekt of is onzeker.")
    if not getattr(result, "purchase_at", None):
        reasons.append("Aankoopdatum ontbreekt of is onzeker.")

    lines = getattr(result, "lines", None) or []
    if not lines:
        reasons.append("Geen artikelregels gevonden.")

    if chosen_total is not None and net_line_sum is not None:
        diff = abs(chosen_total - net_line_sum)
        if diff > Decimal("0.25"):
            reasons.append(f"Totaalbedrag wijkt af van netto som artikelregels met {diff}.")

    if not reasons:
        reasons.append("EssentiÃ«le bongegevens zijn aanwezig en artikelregels zijn bruikbaar voor controle.")

    return {
        "technical_parse_status": parse_status or None,
        "parser_quality_label": label,
        "reasons": reasons,
        "ssot_note": (
            "Deze explainability beschrijft parserkwaliteit. De functionele "
            "Kassa-status komt uitsluitend uit apply_po_norm_status."
        ),
    }


def build_receipt_explainability(result: Any, source_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build generic receipt parser explainability without changing parser decisions.

    Read-only: this explains the existing parser result and must not select a
    different total, article line, OCR route or functional PO status.
    """
    lines = getattr(result, "lines", None) or []
    parser_diagnostics = getattr(result, "parser_diagnostics", None)
    if not isinstance(parser_diagnostics, dict):
        parser_diagnostics = {}

    chosen_total = _safe_decimal(getattr(result, "total_amount", None))
    line_sum = _line_total_sum(lines)
    explicit_discount_total = _safe_decimal(getattr(result, "discount_total", None))
    line_discount_sum = _discount_sum(lines)
    effective_discount = explicit_discount_total if explicit_discount_total is not None else line_discount_sum
    net_line_sum = (line_sum - effective_discount) if line_sum is not None else None

    source = dict(source_context or {}) or {
        "route": "unknown_or_not_recorded",
        "note": "Bronroute-metadata is nog niet persistent vastgelegd; deze laag wijzigt geen parsergedrag.",
    }

    total_candidates = parser_diagnostics.get("total_candidates")
    if not isinstance(total_candidates, list):
        total_candidates = []

    return {
        "version": "R9-07-generic-v1",
        "scope": "generic_all_receipts_all_stores",
        "read_only": True,
        "source_route": source,
        "ocr_route": parser_diagnostics.get("ocr_route") or source.get("ocr_route") or "unknown_or_not_recorded",
        "preprocessing": parser_diagnostics.get("preprocessing") or source.get("preprocessing") or [],
        "header_decisions": {
            "store_name": getattr(result, "store_name", None),
            "purchase_at": getattr(result, "purchase_at", None),
            "total_amount": float(chosen_total) if chosen_total is not None else None,
            "currency": getattr(result, "currency", "EUR"),
        },
        "total_decision": {
            "chosen_total": float(chosen_total) if chosen_total is not None else None,
            "line_sum": float(line_sum) if line_sum is not None else None,
            "effective_discount_total": float(effective_discount) if effective_discount is not None else None,
            "net_line_sum": float(net_line_sum) if net_line_sum is not None else None,
            "difference": float(abs(chosen_total - net_line_sum)) if chosen_total is not None and net_line_sum is not None else None,
            "candidates": total_candidates,
            "note": "Kandidaten worden generiek gerapporteerd zodra een parser ze vastlegt; deze laag kiest zelf geen ander totaal.",
        },
        "article_decisions": {
            "candidate_count": int(parser_diagnostics.get("total_candidates", 0) or 0),
            "appended_count": int(parser_diagnostics.get("appended_candidates", 0) or 0),
            "blocked_count": int(parser_diagnostics.get("blocked_candidates", 0) or 0),
            "by_classification": dict(parser_diagnostics.get("by_classification", {}) or {}),
            "by_blocked_reason": dict(parser_diagnostics.get("by_blocked_reason", {}) or {}),
        },
        "ignored_or_blocked_lines": parser_diagnostics.get("by_blocked_reason", {}) or {},
        "status_explanation": _status_explanation(result, net_line_sum, chosen_total),
    }
