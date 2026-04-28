"""Single source of truth for receipt status classification.

Testfase-regel:
- Alleen twee categorieën: approved en review_needed
- Geen manual in baseline-validatiepad
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

APPROVED = "approved"
REVIEW_NEEDED = "review_needed"
MANUAL = "manual"

STATUS_LABELS = {
    APPROVED: "Gecontroleerd",
    REVIEW_NEEDED: "Controle nodig",
    MANUAL: "Handmatig",
}


@dataclass(frozen=True)
class ReceiptStatusFacts:
    store_name_matches_baseline: bool | None
    total_amount_matches_baseline: bool | None
    article_count_matches_baseline: bool | None
    line_sum_matches_total: bool | None


@dataclass(frozen=True)
class ReceiptStatusDecision:
    parse_status: str
    inbox_status: str
    reason: str


def canonical_parse_status(value: Any) -> str:
    return str(value or "").strip().lower()


def inbox_status_label(value: Any) -> str:
    return STATUS_LABELS.get(value, STATUS_LABELS[REVIEW_NEEDED])


def normalize_receipt_status_fields(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row or {})
    status = canonical_parse_status(normalized.get("parse_status"))
    normalized["parse_status"] = status
    normalized["status"] = STATUS_LABELS.get(status, STATUS_LABELS[REVIEW_NEEDED])
    normalized["inbox_status"] = normalized["status"]
    return normalized


def decide_receipt_status_from_facts(
    *,
    store_name_matches_baseline: bool | None,
    total_amount_matches_baseline: bool | None,
    article_count_matches_baseline: bool | None,
    line_sum_matches_total: bool | None,
) -> ReceiptStatusDecision:

    facts = [
        store_name_matches_baseline,
        total_amount_matches_baseline,
        article_count_matches_baseline,
        line_sum_matches_total,
    ]

    if all(value is True for value in facts):
        return ReceiptStatusDecision(
            parse_status=APPROVED,
            inbox_status=STATUS_LABELS[APPROVED],
            reason="approved: voldoet aan alle baseline-feiten",
        )

    return ReceiptStatusDecision(
        parse_status=REVIEW_NEEDED,
        inbox_status=STATUS_LABELS[REVIEW_NEEDED],
        reason="review_needed: voldoet niet aan baseline-feiten",
    )


def decide_receipt_status(**kwargs) -> ReceiptStatusDecision:
    return decide_receipt_status_from_facts(**kwargs)
