"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: no
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics
from app.receipt_ingestion.text_encoding_normalization import normalize_receipt_text_encoding


def _normalize_result_line_encodings(lines: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Normalize parser result labels without changing the preserved raw label."""
    normalized_lines: list[dict[str, Any]] = []
    for line in lines or []:
        if not isinstance(line, dict):
            normalized_lines.append(line)
            continue
        item = dict(line)
        label_source = item.get('normalized_label') or item.get('raw_label')
        normalized_label, encoding_metadata = normalize_receipt_text_encoding(label_source)
        if normalized_label:
            item['normalized_label'] = normalized_label
        if encoding_metadata:
            trace = item.get('producer_trace')
            if not isinstance(trace, dict):
                trace = {}
            trace.update({
                'encoding_normalization_applied': True,
                'encoding_original_text': encoding_metadata.get('original_text'),
                'encoding_normalized_text': encoding_metadata.get('normalized_text'),
                'encoding_replacements': encoding_metadata.get('encoding_replacements'),
                'encoding_normalization_stage': 'receipt_result',
            })
            item['producer_trace'] = trace
        normalized_lines.append(item)
    return normalized_lines


@dataclass(init=False)
class ReceiptParseResult:
    """Parser result DTO with an explicit constructor contract.

    R9-36E guardrail: the active parser calls ReceiptParseResult(...) with
    keyword arguments in multiple code paths. The constructor must therefore be
    explicit and stable, independent of dataclass auto-init generation.
    """

    is_receipt: bool
    parse_status: str
    confidence_score: float | None
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    discount_total: Decimal | None
    currency: str
    lines: list[dict[str, Any]] | None
    store_branch: str | None
    parser_diagnostics: dict[str, Any] | None

    def __init__(
        self,
        *,
        is_receipt: bool,
        parse_status: str,
        confidence_score: float | None,
        store_name: str | None,
        purchase_at: str | None,
        total_amount: Decimal | None,
        discount_total: Decimal | None = None,
        currency: str = 'EUR',
        lines: list[dict[str, Any]] | None = None,
        store_branch: str | None = None,
        parser_diagnostics: dict[str, Any] | None = None,
    ) -> None:
        self.is_receipt = bool(is_receipt)
        self.parse_status = str(parse_status or '')
        self.confidence_score = confidence_score
        self.store_name = store_name
        self.purchase_at = purchase_at
        self.total_amount = total_amount
        self.discount_total = discount_total
        self.currency = currency or 'EUR'
        self.lines = _normalize_result_line_encodings(lines)
        self.store_branch = store_branch
        self.parser_diagnostics = parser_diagnostics



def _result_decimal(value: Any) -> Decimal:
    try:
        if value is None or value == '':
            return Decimal('0.00')
        return Decimal(str(value))
    except Exception:
        return Decimal('0.00')


def _receipt_result_line_sum(lines: list[dict[str, Any]] | None) -> Decimal:
    return sum((_result_decimal(line.get('line_total')) for line in (lines or []) if isinstance(line, dict)), Decimal('0.00'))


def _receipt_result_line_discount_sum(lines: list[dict[str, Any]] | None) -> Decimal:
    return sum((_result_decimal(line.get('discount_amount')) for line in (lines or []) if isinstance(line, dict)), Decimal('0.00'))


def _receipt_result_net_sum(parse_result: ReceiptParseResult) -> Decimal:
    return (
        _receipt_result_line_sum(parse_result.lines)
        + _receipt_result_line_discount_sum(parse_result.lines)
        + _result_decimal(parse_result.discount_total)
    )


def _receipt_result_total_diff(parse_result: ReceiptParseResult) -> Decimal | None:
    if parse_result.total_amount is None:
        return None
    try:
        return abs(_receipt_result_net_sum(parse_result) - Decimal(str(parse_result.total_amount)))
    except Exception:
        return None


def _has_blocking_parser_diagnostic(parse_result: ReceiptParseResult) -> bool:
    diagnostics = parse_result.parser_diagnostics or {}
    if not isinstance(diagnostics, dict):
        return False
    blocking_flags = (
        'blocking_error',
        'parse_blocked',
        'guardrail_failed',
        'replacement_valid_false',
    )
    return any(bool(diagnostics.get(flag)) for flag in blocking_flags)


def determine_final_parse_status(parse_result: ReceiptParseResult) -> str:
    """Baseline-onafhankelijke eindstatus voor kassabonnen.

    R9-38D1:
    De runtime-status mag niet afhankelijk zijn van de PO-baseline. De baseline
    blijft test- en regressie-orakel. Een bon mag automatisch 'approved' worden
    wanneer de parseroutput zelf sluitend is:
    - bruikbare bon;
    - winkel en totaal aanwezig;
    - minimaal één bonregel;
    - volledige nettoformule sluit exact aan:
      sum(line_total) + sum(discount_amount) + discount_total = total_amount;
    - geen blocking parserdiagnostic.
    """
    if not parse_result or not parse_result.is_receipt:
        return 'failed'

    has_store = bool(str(parse_result.store_name or '').strip())
    has_total = parse_result.total_amount is not None

    if not has_store or not has_total:
        return 'review_needed'

    lines = parse_result.lines or []
    if not lines:
        return 'parsed'

    if _has_blocking_parser_diagnostic(parse_result):
        return 'review_needed'

    total_diff = _receipt_result_total_diff(parse_result)

    # Strong, baseline-independent acceptance.
    if total_diff is not None and total_diff <= Decimal('0.02') and len(lines) >= 1:
        return 'approved'

    # Weak but usable: header is good, but article extraction needs possible review.
    if total_diff is not None and total_diff <= Decimal('0.25'):
        return 'parsed'

    return 'review_needed'


def _line_decimal_total(line: dict[str, Any]) -> Decimal:
    return _parse_decimal(str(line.get('line_total'))) or Decimal('0.00')



def _discount_decimal_total(line: dict[str, Any]) -> Decimal:
    return _parse_decimal(str(line.get('discount_amount'))) or Decimal('0.00')



def _result_quality_score(result: ReceiptParseResult) -> tuple[int, int, int, int, int]:
    if not result.is_receipt:
        return (0, 0, 0, 0, 0)
    line_count = len(result.lines or [])
    has_total = 1 if result.total_amount is not None else 0
    has_store = 1 if result.store_name else 0
    has_purchase = 1 if result.purchase_at else 0
    total_match = 0
    if result.total_amount is not None and line_count:
        line_sum = sum((_line_decimal_total(line) for line in result.lines), Decimal('0.00'))
        line_discount_sum = sum((_discount_decimal_total(line) for line in result.lines), Decimal('0.00'))
        receipt_discount_sum = result.discount_total if result.discount_total is not None else Decimal('0.00')
        if receipt_discount_sum is None:
            receipt_discount_sum = Decimal('0.00')
        try:
            if abs((line_sum + line_discount_sum + receipt_discount_sum) - result.total_amount) < Decimal('0.011'):
                total_match = 1
        except Exception:
            total_match = 0
    status_weight = {'approved': 4, 'parsed': 3, 'partial': 2, 'review_needed': 1, 'failed': 0}.get(str(result.parse_status or ''), 0)
    return (has_total + has_store + has_purchase + total_match, status_weight, line_count, has_total, total_match)



def _choose_better_receipt_result(primary: ReceiptParseResult, secondary: ReceiptParseResult) -> ReceiptParseResult:
    primary_score = _result_quality_score(primary)
    secondary_score = _result_quality_score(secondary)
    return secondary if secondary_score > primary_score else primary



def _failed_receipt_result(confidence: float = 0.0) -> ReceiptParseResult:
    return ReceiptParseResult(
        is_receipt=False,
        parse_status='failed',
        confidence_score=confidence,
        store_name=None,
        purchase_at=None,
        total_amount=None,
        discount_total=None,
        currency='EUR',
        lines=[],
        parser_diagnostics=summarize_lines_parser_diagnostics([]),
    )
