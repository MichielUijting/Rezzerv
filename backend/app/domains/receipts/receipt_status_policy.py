"""Single source of truth for receipt status classification.

This module deliberately contains the only canonical mapping between technical
parse statuses and the user-facing Kassa categories. Baseline diagnostics,
admin recompute endpoints and API serializers should depend on this policy
instead of duplicating status/category logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

APPROVED = "approved"
REVIEW_NEEDED = "review_needed"
MANUAL = "manual"

STATUS_LABELS = {
    APPROVED: "Gecontroleerd",
    REVIEW_NEEDED: "Controle nodig",
    MANUAL: "Handmatig",
}

APPROVED_ALIASES = {"approved", "parsed", "approved_override", "gecontroleerd", "goedgekeurd", "geparsed"}
REVIEW_NEEDED_ALIASES = {"review_needed", "partial", "controle nodig", "gedeeltelijk herkend", "niet herkend"}
MANUAL_ALIASES = {"manual", "handmatig", "failed", "nieuw"}

INVALID_STORE_NAMES = {"", "onbekend", "unknown", "n.v.t.", "nvt", "onbekende winkel"}


@dataclass(frozen=True)
class ReceiptStatusDecision:
    parse_status: str
    inbox_status: str
    reason: str
    store_name_ok: bool
    total_amount_ok: bool
    article_count_ok: bool
    line_sum_matches_total: bool


def to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def amount_matches(left: Any, right: Any, tolerance: Decimal = Decimal("0.01")) -> bool:
    left_dec = to_decimal(left)
    right_dec = to_decimal(right)
    if left_dec is None or right_dec is None:
        return False
    return abs(left_dec - right_dec) <= tolerance


def canonical_parse_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in APPROVED_ALIASES:
        return APPROVED
    if normalized in REVIEW_NEEDED_ALIASES:
        return REVIEW_NEEDED
    if normalized in MANUAL_ALIASES:
        return MANUAL
    return normalized or MANUAL


def inbox_status_label(value: Any) -> str:
    return STATUS_LABELS.get(canonical_parse_status(value), STATUS_LABELS[MANUAL])


def normalize_receipt_status_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with parse_status and inbox_status derived from one policy."""
    normalized = dict(row or {})
    canonical = canonical_parse_status(normalized.get("parse_status") or normalized.get("status") or normalized.get("inbox_status"))
    normalized["parse_status"] = canonical
    normalized["status"] = STATUS_LABELS[canonical]
    normalized["inbox_status"] = STATUS_LABELS[canonical]
    return normalized


def decide_receipt_status(
    *,
    store_name: Any,
    total_amount: Any,
    article_count: Any,
    line_total_sum: Any,
    discount_total: Any = None,
    totals_overridden: Any = False,
) -> ReceiptStatusDecision:
    """Classify a receipt without consulting UI, baseline files or PO criteria docs."""
    store_name_text = str(store_name or "").strip().lower()
    store_name_ok = store_name_text not in INVALID_STORE_NAMES
    total_dec = to_decimal(total_amount)
    total_amount_ok = total_dec is not None
    try:
        article_count_ok = int(article_count or 0) > 0
    except (ValueError, TypeError):
        article_count_ok = False

    line_sum = to_decimal(line_total_sum) or Decimal("0.00")
    discount = to_decimal(discount_total) or Decimal("0.00")
    net_line_sum = line_sum + discount
    line_sum_matches_total = total_amount_ok and amount_matches(total_dec, net_line_sum)

    if bool(totals_overridden):
        parse_status = APPROVED
        reason = "approved: totalen zijn handmatig gecorrigeerd"
    elif not store_name_ok or not total_amount_ok or not article_count_ok:
        parse_status = MANUAL
        if not store_name_ok:
            reason = "manual: winkelnaam ontbreekt of is ongeldig"
        elif not total_amount_ok:
            reason = "manual: totaalprijs ontbreekt of is ongeldig"
        else:
            reason = "manual: geen geldige artikellijnen gevonden"
    elif line_sum_matches_total:
        parse_status = APPROVED
        reason = "approved: winkelnaam, totaalprijs en regelsom sluiten volgens centrale policy"
    else:
        parse_status = REVIEW_NEEDED
        reason = "review_needed: regelsom sluit niet op totaalprijs volgens centrale policy"

    return ReceiptStatusDecision(
        parse_status=parse_status,
        inbox_status=STATUS_LABELS[parse_status],
        reason=reason,
        store_name_ok=store_name_ok,
        total_amount_ok=total_amount_ok,
        article_count_ok=article_count_ok,
        line_sum_matches_total=bool(line_sum_matches_total),
    )
