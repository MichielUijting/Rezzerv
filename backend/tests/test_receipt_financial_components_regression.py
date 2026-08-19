from decimal import Decimal

from app.receipt_ingestion.line_classifier import (
    classify_receipt_text_line,
    receipt_financial_candidate_line_type,
)
from app.receipt_ingestion.product_candidate_gateway import append_product_candidate
from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.receipt_ingestion.service_parts.receipt_result_helpers import (
    ReceiptParseResult,
    determine_final_parse_status,
)


def _parse_decimal(value):
    if value in (None, ''):
        return None
    return Decimal(str(value).replace(',', '.'))


def _amount_to_float(value):
    return None if value is None else float(value)


def _append_financial(label: str, amount: str):
    extracted = []
    index = append_product_candidate(
        extracted,
        label=label,
        qty_raw=None,
        amount1_raw=amount,
        amount2_raw=None,
        source_index=0,
        raw_line=f'{label} {amount}',
        normalized_line=f'{label} {amount}',
        filename='opaque.jpeg',
        store_name='opaque',
        function_name='_extract_receipt_lines',
        append_branch='append_line',
        parser_path='_extract_receipt_lines.append_line',
        caller_line_hint='financial regression contract',
        clean_label=lambda value: str(value or '').strip(),
        parse_quantity=lambda value: _parse_decimal(value),
        parse_decimal=_parse_decimal,
        amount_to_float=_amount_to_float,
        classify_line=lambda value: classify_receipt_text_line(value),
        is_invalid_label=lambda value: True,
        confidence_score=0.95,
    )
    assert index == 0
    assert len(extracted) == 1
    return extracted[0]


def _result(total: str, lines: list[dict]) -> ReceiptParseResult:
    return ReceiptParseResult(
        is_receipt=True,
        parse_status='review_needed',
        confidence_score=0.95,
        store_name='opaque',
        purchase_at='2026-01-01T12:00:00',
        total_amount=Decimal(total),
        discount_total=None,
        currency='EUR',
        lines=lines,
        parser_diagnostics=None,
    )


def test_pr244_regression_boundary_keeps_priced_financial_components_parseable():
    assert classify_receipt_text_line('Statiegeld 0,25') == 'product_candidate'
    assert classify_receipt_text_line('Emballage 0,50') == 'product_candidate'
    assert classify_receipt_text_line('Verzendkosten 4,95') == 'product_candidate'
    assert classify_receipt_text_line('In prijs verlaagd -0,20') == 'product_candidate'

    # Headers/footers remain excluded: only priced financial components are promoted.
    assert classify_receipt_text_line('Statiegeld') == 'footer_payment_tax'
    assert classify_receipt_text_line('Totaal 12,24') == 'footer_payment_tax'
    assert classify_receipt_text_line('VISA 12,24') == 'footer_payment_tax'


def test_financial_candidate_subtypes_are_canonical_and_non_inventory():
    cases = (
        ('Statiegeld', '0,25', 'deposit'),
        ('Emballage retour', '-0,50', 'deposit'),
        ('Verzendkosten', '4,95', 'shipping'),
        ('In prijs verlaagd', '-0,20', 'discount'),
    )
    for label, amount, expected_type in cases:
        assert receipt_financial_candidate_line_type(label, has_amount=True) == expected_type
        line = _append_financial(label, amount)
        assert line['line_type'] == expected_type
        semantics = derive_receipt_line_semantics(line)
        assert semantics == {'line_role': 'financial', 'inventory_eligible': False}


def test_ah_statiegeld_reconciliation_returns_to_approved():
    lines = [
        {'line_type': 'product', 'raw_label': 'P1', 'line_total': 3.05},
        {'line_type': 'product', 'raw_label': 'P2', 'line_total': 1.29},
        {'line_type': 'product', 'raw_label': 'P3', 'line_total': 7.65},
        _append_financial('Statiegeld', '0,25'),
    ]
    assert determine_final_parse_status(_result('12.24', lines)) == 'approved'


def test_lidl_deposits_and_price_reductions_reconcile_exactly():
    # Observed regression: physical product rows totalled 67.83 while the receipt
    # total was 69.33. Two deposits (+1.80) and two price reductions (-0.30)
    # are financial, non-inventory components and close the receipt exactly.
    lines = [
        {'line_type': 'product', 'raw_label': 'physical product aggregate', 'line_total': 67.83},
        _append_financial('Ger. statiegeld', '0,60'),
        _append_financial('Blik 8-pack statiegeld', '1,20'),
        _append_financial('In prijs verlaagd', '-0,20'),
        _append_financial('In prijs verlaagd', '-0,10'),
    ]
    assert determine_final_parse_status(_result('69.33', lines)) == 'approved'
