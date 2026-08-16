from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult

from .errors import ContractValidationError
from .schemas.canonical_receipt_v1 import CanonicalReceiptV1


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _to_legacy_line_number(value: Any) -> float | None:
    """Restore the pre-scanner ReceiptParseResult numeric boundary."""
    if value is None or value == "":
        return None
    return float(Decimal(str(value)))


def _purchase_at_from_canonical(value: CanonicalReceiptV1) -> str | None:
    if value.receipt is None:
        return None
    transaction = value.receipt.transaction
    if transaction.purchase_date is None:
        return None
    if transaction.purchase_time is None:
        return transaction.purchase_date.isoformat()
    return datetime.combine(transaction.purchase_date, transaction.purchase_time).isoformat()


def canonical_to_receipt_parse_result(value: CanonicalReceiptV1) -> ReceiptParseResult:
    """Translate scanner observations without reinterpreting receipt text.

    Canonical ``line_type`` and scanner quality are preserved as structured
    facts. Downstream business routing must consume these facts instead of
    reclassifying raw/description text or reconstructing scanner confidence.
    """
    if value.status == "failed":
        confidence = getattr(value, "_legacy_confidence_score", None)
        return ReceiptParseResult(
            is_receipt=False,
            parse_status=getattr(value, "_legacy_parse_status", None) or "failed",
            confidence_score=confidence,
            store_name=None,
            purchase_at=None,
            total_amount=None,
            discount_total=None,
            currency="EUR",
            lines=[],
            parser_diagnostics=getattr(value, "_legacy_parser_diagnostics", None) or summarize_lines_parser_diagnostics([]),
        )
    if value.status != "completed" or value.receipt is None:
        raise ContractValidationError(f"Cannot normalize scanner status {value.status!r} into persisted receipt data")

    receipt = value.receipt
    lines: list[dict[str, Any]] = []
    for line in receipt.lines:
        line_confidence = None
        if line.confidence is not None:
            line_confidence = line.confidence.line_total if line.confidence.line_total is not None else line.confidence.description
        barcode = None
        if line.identifiers is not None:
            barcode = line.identifiers.gtin or line.identifiers.barcode
        lines.append({
            "line_type": line.line_type,
            "raw_label": line.raw_text,
            "normalized_label": line.description or line.raw_text,
            "quantity": _to_legacy_line_number(line.quantity),
            "unit": line.unit,
            "unit_price": _to_legacy_line_number(line.unit_price),
            "line_total": _to_legacy_line_number(line.line_total),
            "discount_amount": _to_legacy_line_number(line.discount_amount),
            "barcode": barcode,
            "confidence_score": line_confidence,
        })

    parser_diagnostics = getattr(value, "_legacy_parser_diagnostics", None)
    canonical_parse_status = "review_needed"
    if value.quality is not None and value.quality.requires_review is False:
        canonical_parse_status = "approved"

    return ReceiptParseResult(
        is_receipt=True,
        parse_status=canonical_parse_status,
        confidence_score=value.quality.overall_confidence if value.quality else None,
        store_name=receipt.store.name,
        store_branch=receipt.store.branch_name,
        purchase_at=_purchase_at_from_canonical(value),
        total_amount=_to_decimal(receipt.totals.grand_total),
        discount_total=_to_decimal(receipt.totals.discount_total),
        currency=receipt.transaction.currency or "EUR",
        lines=lines,
        parser_diagnostics=parser_diagnostics or summarize_lines_parser_diagnostics(lines),
    )
