from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected anchor exactly once, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


line_classifier = ROOT / "backend/app/receipt_ingestion/line_classifier.py"
gateway = ROOT / "backend/app/receipt_ingestion/product_candidate_gateway.py"
inventory_test = ROOT / "backend/tests/test_receipt_inventory_eligibility.py"
regression_test = ROOT / "backend/tests/test_receipt_financial_components_regression.py"

replace_once(
    line_classifier,
    """GENERIC_DISCOUNT_TOKENS = (
    'korting', 'bonus', 'actie', 'prijsvoordeel', 'jouw voordeel', 'uw voordeel',
    'lidl plus korting', 'totaal korting', 'coupon', 'voucher', 'gratis',
    'in prijs verlaagd', 'prijs verlaagd', 'prijsverlaging', 'afgeprijsd',
    'reduced price', 'price reduction',
)
""",
    """GENERIC_PRICE_REDUCTION_TOKENS = (
    'in prijs verlaagd', 'prijs verlaagd', 'prijsverlaging', 'afgeprijsd',
    'reduced price', 'price reduction',
)
GENERIC_DISCOUNT_TOKENS = (
    'korting', 'bonus', 'actie', 'prijsvoordeel', 'jouw voordeel', 'uw voordeel',
    'lidl plus korting', 'totaal korting', 'coupon', 'voucher', 'gratis',
) + GENERIC_PRICE_REDUCTION_TOKENS
""",
)

replace_once(
    line_classifier,
    """GENERIC_NON_INVENTORY_CHARGE_TOKENS = (
    'statiegeld retour', 'retour statiegeld', 'emballage retour', 'fust retour',
    'statiegeld', 'emballage', 'fust',
    'verzendkosten', 'verzend kosten', 'bezorgkosten', 'bezorg kosten',
    'shipping fee', 'delivery fee',
)
""",
    """GENERIC_DEPOSIT_TOKENS = (
    'statiegeld retour', 'retour statiegeld', 'emballage retour', 'fust retour',
    'statiegeld', 'emballage', 'fust',
)
GENERIC_SHIPPING_TOKENS = (
    'verzendkosten', 'verzend kosten', 'bezorgkosten', 'bezorg kosten',
    'shipping fee', 'delivery fee',
)
GENERIC_NON_INVENTORY_CHARGE_TOKENS = GENERIC_DEPOSIT_TOKENS + GENERIC_SHIPPING_TOKENS
""",
)

replace_once(
    line_classifier,
    """def _priced_article_value_token(lowered: str) -> str | None:
""",
    """def receipt_financial_candidate_line_type(
    line: str,
    *,
    has_amount: bool = True,
) -> str | None:
    \"\"\"Return the canonical type for a priced non-inventory receipt component.

    This function belongs to the ingestion classifier layer: receipt text may be
    inspected here, but downstream business semantics must consume only the
    canonical ``line_type`` produced from this decision.

    A label without a parsed amount is never promoted to a financial candidate;
    this keeps headers, explanatory text, totals and payment metadata out of the
    persisted logical receipt lines.
    \"\"\"
    if not has_amount:
        return None
    lowered = re.sub(r'\\s+', ' ', str(line or '')).strip().lower()
    if not lowered:
        return None
    if _token_match(lowered, GENERIC_DEPOSIT_TOKENS):
        return 'deposit'
    if _token_match(lowered, GENERIC_SHIPPING_TOKENS):
        return 'shipping'
    if _token_match(lowered, GENERIC_PRICE_REDUCTION_TOKENS):
        return 'discount'
    return None


def _priced_article_value_token(lowered: str) -> str | None:
""",
)

replace_once(
    line_classifier,
    """    lowered = normalized.lower()
    upper = normalized.upper().replace(',', '.')
    supporting_amount_token = _token_match(lowered, GENERIC_SUPPORTING_AMOUNT_DETAIL_TOKENS)
""",
    """    lowered = normalized.lower()
    upper = normalized.upper().replace(',', '.')
    financial_line_type = receipt_financial_candidate_line_type(
        normalized,
        has_amount=_has_amount(lowered),
    )
    if financial_line_type is not None:
        if financial_line_type == 'deposit':
            matched = _token_match(lowered, GENERIC_DEPOSIT_TOKENS)
        elif financial_line_type == 'shipping':
            matched = _token_match(lowered, GENERIC_SHIPPING_TOKENS)
        else:
            matched = _token_match(lowered, GENERIC_PRICE_REDUCTION_TOKENS)
        return _decision(
            'product_candidate',
            'GENERIC_PRICED_FINANCIAL_COMPONENT',
            matched,
        )
    supporting_amount_token = _token_match(lowered, GENERIC_SUPPORTING_AMOUNT_DETAIL_TOKENS)
""",
)

replace_once(
    gateway,
    """from app.receipt_ingestion.line_classifier import classification_allows_append
""",
    """from app.receipt_ingestion.line_classifier import (
    classification_allows_append,
    receipt_financial_candidate_line_type,
)
""",
)

replace_once(
    gateway,
    """    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None

    ah_leading_quantity_metadata = None
""",
    """    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None

    financial_line_type = receipt_financial_candidate_line_type(
        label_value,
        has_amount=(amount1_raw is not None or amount2_raw is not None),
    )

    ah_leading_quantity_metadata = None
""",
)

replace_once(
    gateway,
    """    if is_invalid_label is not None and is_invalid_label(label_value) and not savings_action_path:
        return None
""",
    """    if (
        is_invalid_label is not None
        and is_invalid_label(label_value)
        and not savings_action_path
        and financial_line_type is None
    ):
        return None
""",
)

replace_once(
    gateway,
    """    append_allowed = classification_allowed or savings_action_path
""",
    """    append_allowed = classification_allowed or savings_action_path or financial_line_type is not None
""",
)

replace_once(
    gateway,
    """    raw_label_value = clean_label(raw_line) if savings_action_path and raw_line else (ah_leading_quantity_metadata.get('original_label') if ah_leading_quantity_metadata else label_value)
    label_value, quantity, unit_value, package_metadata = apply_package_extraction_to_candidate(label_value, quantity=quantity, unit='kg' if qty_raw and 'kg' in qty_raw.lower() else None)
    label_value, quantity, name_metadata = normalize_product_name_label(
        label_value,
        quantity=quantity,
        transaction_text=normalized_line or raw_line,
        unit_price=unit_price,
        line_total=line_total,
    )
    raw_label_value = raw_label_value or label_value
""",
    """    raw_label_value = clean_label(raw_line) if savings_action_path and raw_line else (ah_leading_quantity_metadata.get('original_label') if ah_leading_quantity_metadata else label_value)
    package_metadata = None
    name_metadata = None
    unit_value = 'kg' if qty_raw and 'kg' in qty_raw.lower() else None
    if financial_line_type is None:
        label_value, quantity, unit_value, package_metadata = apply_package_extraction_to_candidate(
            label_value,
            quantity=quantity,
            unit=unit_value,
        )
        label_value, quantity, name_metadata = normalize_product_name_label(
            label_value,
            quantity=quantity,
            transaction_text=normalized_line or raw_line,
            unit_price=unit_price,
            line_total=line_total,
        )
    raw_label_value = raw_label_value or label_value
""",
)

replace_once(
    gateway,
    """    candidate_line = {
        'line_type': 'product',
""",
    """    candidate_line = {
        'line_type': financial_line_type or 'product',
""",
)

replace_once(
    gateway,
    """        'classification_trace': classification_trace, 'validated_savings_action_path': savings_action_path,
    }
    if encoding_metadata:
""",
    """        'classification_trace': classification_trace, 'validated_savings_action_path': savings_action_path,
    }
    if financial_line_type is not None:
        producer_trace.update({
            'line_type': financial_line_type,
            'financial_candidate': True,
            'include_in_receipt_total': True,
            'exclude_from_inventory': True,
            'external_matching_allowed': False,
        })
    if encoding_metadata:
""",
)

inventory_test.write_text(
    """from pathlib import Path

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics


def test_canonical_product_is_inventory_product():
    result = derive_receipt_line_semantics({
        'line_type': 'product',
        'raw_label': 'opaque product label',
    })
    assert result == {'line_role': 'product', 'inventory_eligible': True}


def test_canonical_loyalty_is_not_inventory():
    result = derive_receipt_line_semantics({
        'line_type': 'loyalty',
        'raw_label': 'opaque loyalty label',
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_canonical_financial_types_are_not_inventory():
    for line_type in ('discount', 'deposit', 'shipping', 'fee', 'tax', 'payment', 'total'):
        result = derive_receipt_line_semantics({
            'line_type': line_type,
            'raw_label': f'opaque {line_type} label',
        })
        assert result['line_role'] == 'financial', line_type
        assert result['inventory_eligible'] is False, line_type


def test_untyped_line_fails_closed():
    result = derive_receipt_line_semantics({'raw_label': 'Onbekende tekst'})
    assert result == {'line_role': 'unknown', 'inventory_eligible': False}


def test_persisted_semantics_are_authoritative():
    result = derive_receipt_line_semantics({
        'line_type': 'product',
        'raw_label': 'arbitrary display text',
        'line_role': 'loyalty',
        'inventory_eligible': 0,
    })
    assert result == {'line_role': 'loyalty', 'inventory_eligible': False}


def test_semantic_columns_live_in_central_receipt_schema_evolution():
    source = (Path(__file__).resolve().parents[1] / 'app/main.py').read_text(encoding='utf-8')
    start = source.index('line_additions = {')
    block = source[start:start + 1200]
    assert \"'line_role': 'TEXT'\" in block
    assert \"'inventory_eligible': 'INTEGER'\" in block


def test_receipt_service_persists_semantics_on_both_ingest_paths():
    source = (Path(__file__).resolve().parents[1] / 'app/services/receipt_service.py').read_text(encoding='utf-8')
    assert source.count('INSERT INTO receipt_table_lines') == 2
    assert source.count('line_role, inventory_eligible') == 2
    assert source.count('semantics = derive_receipt_line_semantics(line, store_name=parse_result.store_name)') == 2
    assert source.count(\"'line_role': semantics['line_role']\") == 2
    assert source.count(\"'inventory_eligible': 1 if semantics['inventory_eligible'] else 0\") == 2
""",
    encoding="utf-8",
)

regression_test.write_text(
    """from decimal import Decimal

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
""",
    encoding="utf-8",
)

print("Kassa financial regression patch staged.")
