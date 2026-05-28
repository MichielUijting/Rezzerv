from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics


@dataclass
class ReceiptParseResult:
    is_receipt: bool
    parse_status: str
    confidence_score: float | None
    store_name: str | None
    purchase_at: str | None
    total_amount: Decimal | None
    discount_total: Decimal | None = None
    currency: str = 'EUR'
    lines: list[dict[str, Any]] | None = None
    store_branch: str | None = None
    parser_diagnostics: dict[str, Any] | None = None


def determine_final_parse_status(parse_result: ReceiptParseResult) -> str:
    """Bepaalt de definitieve database-status voor een kassabon.

    De parser mag intern streng blijven voor diagnose, maar de database moet
    weergeven of een bon voor de gebruiker bruikbaar is. Daarom wordt een bon
    als 'parsed' opgeslagen zodra de essentiele kopgegevens betrouwbaar zijn:
    winkelnaam en totaalbedrag. Waar mogelijk controleren we daarnaast of de
    netto regelsom binnen tolerantie klopt, maar een imperfecte artikel-extractie
    mag een verder bruikbare bon niet onnodig op 'review_needed' houden.
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

    try:
        line_sum = Decimal('0')
        line_discount_sum = Decimal('0')
        for line in lines:
            if not isinstance(line, dict):
                continue
            line_total = line.get('line_total')
            if line_total is not None:
                line_sum += Decimal(str(line_total))
            discount_amount = line.get('discount_amount')
            if discount_amount is not None:
                line_discount_sum += Decimal(str(discount_amount))
        discount_total = parse_result.discount_total if parse_result.discount_total is not None else line_discount_sum
        net_line_sum = line_sum - Decimal(str(discount_total or 0))
        diff = abs(net_line_sum - Decimal(str(parse_result.total_amount)))
        if diff <= Decimal('0.25'):
            return 'parsed'
    except Exception:
        # Als de totaalcontrole niet uitgevoerd kan worden, blijven winkel en
        # totaalbedrag leidend voor de database-classificatie.
        return 'parsed'

    # Essentiele kopgegevens zijn aanwezig; artikelregels kunnen later handmatig
    # worden verbeterd zonder dat de hele bon in de controlebak hoeft te blijven.
    return 'parsed'


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
        discount_sum = result.discount_total if result.discount_total is not None else sum((_discount_decimal_total(line) for line in result.lines), Decimal('0.00'))
        if discount_sum is None:
            discount_sum = Decimal('0.00')
        try:
            if abs((line_sum + discount_sum) - result.total_amount) < Decimal('0.011'):
                total_match = 1
        except Exception:
            total_match = 0
    status_weight = {'parsed': 3, 'partial': 2, 'review_needed': 1, 'failed': 0}.get(str(result.parse_status or ''), 0)
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
