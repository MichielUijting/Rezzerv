"""Single source of truth for receipt status classification.

Architecture rule for the receipt test phase:
OCR/parsing and baseline comparison produce facts. This policy only decides the
category from those facts. It must not perform OCR/parsing interpretation itself.
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
    store_name_matches_baseline: bool | None = None
    total_amount_matches_baseline: bool | None = None
    article_count_matches_baseline: bool | None = None
    line_sum_matches_total: bool | None = None

    @property
    def store_name_ok(self) -> bool:
        return bool(self.store_name_matches_baseline)

    @property
    def total_amount_ok(self) -> bool:
        return bool(self.total_amount_matches_baseline)

    @property
    def article_count_ok(self) -> bool:
        return bool(self.article_count_matches_baseline)


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
    normalized = dict(row or {})
    canonical = canonical_parse_status(normalized.get("parse_status") or normalized.get("status") or normalized.get("inbox_status"))
    normalized["parse_status"] = canonical
    normalized["status"] = STATUS_LABELS[canonical]
    normalized["inbox_status"] = STATUS_LABELS[canonical]
    return normalized


def decide_receipt_status_from_facts(
    *,
    store_name_matches_baseline: bool | None,
    total_amount_matches_baseline: bool | None,
    article_count_matches_baseline: bool | None,
    line_sum_matches_total: bool | None,
) -> ReceiptStatusDecision:
    facts = ReceiptStatusFacts(
        store_name_matches_baseline=store_name_matches_baseline,
        total_amount_matches_baseline=total_amount_matches_baseline,
        article_count_matches_baseline=article_count_matches_baseline,
        line_sum_matches_total=line_sum_matches_total,
    )
    if any(value is None for value in facts.__dict__.values()):
        parse_status = MANUAL
        reason = "manual: baselinevergelijking is niet volledig mogelijk"
    elif all(facts.__dict__.values()):
        parse_status = APPROVED
        reason = "approved: winkel, totaal, artikelaantal en regelsom voldoen aan de baseline-policy"
    else:
        parse_status = REVIEW_NEEDED
        failed = [
            name for name, value in facts.__dict__.items()
            if value is False
        ]
        reason = "review_needed: baseline-policy faalt op " + ", ".join(failed)
    return ReceiptStatusDecision(
        parse_status=parse_status,
        inbox_status=STATUS_LABELS[parse_status],
        reason=reason,
        store_name_matches_baseline=facts.store_name_matches_baseline,
        total_amount_matches_baseline=facts.total_amount_matches_baseline,
        article_count_matches_baseline=facts.article_count_matches_baseline,
        line_sum_matches_total=facts.line_sum_matches_total,
    )


def decide_receipt_status(
    *,
    store_name_matches_baseline: bool | None = None,
    total_amount_matches_baseline: bool | None = None,
    article_count_matches_baseline: bool | None = None,
    line_sum_matches_total: bool | None = None,
    store_name: Any = None,
    total_amount: Any = None,
    article_count: Any = None,
    line_total_sum: Any = None,
    discount_total: Any = None,
    totals_overridden: Any = False,
) -> ReceiptStatusDecision:
    """Compatibility entrypoint.

    Preferred use is facts-only. Legacy runtime callers without baseline facts are
    intentionally mapped to manual instead of silently making a category decision.
    """
    if any(
        value is not None
        for value in (
            store_name_matches_baseline,
            total_amount_matches_baseline,
            article_count_matches_baseline,
            line_sum_matches_total,
        )
    ):
        return decide_receipt_status_from_facts(
            store_name_matches_baseline=store_name_matches_baseline,
            total_amount_matches_baseline=total_amount_matches_baseline,
            article_count_matches_baseline=article_count_matches_baseline,
            line_sum_matches_total=line_sum_matches_total,
        )

    return ReceiptStatusDecision(
        parse_status=MANUAL,
        inbox_status=STATUS_LABELS[MANUAL],
        reason="manual: geen baselinevergelijkingsfeiten aangeleverd aan centrale policy",
        store_name_matches_baseline=None,
        total_amount_matches_baseline=None,
        article_count_matches_baseline=None,
        line_sum_matches_total=None,
    )
