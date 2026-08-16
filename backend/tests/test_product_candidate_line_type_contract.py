from decimal import Decimal

from app.receipt_ingestion.product_candidate_gateway import append_product_candidate


def _append(label: str = 'opaque-product'):
    extracted = []
    index = append_product_candidate(
        extracted,
        label=label,
        qty_raw=None,
        amount1_raw='2.50',
        amount2_raw=None,
        source_index=1,
        raw_line=f'{label} 2.50',
        normalized_line=f'{label} 2.50',
        filename='opaque.pdf',
        store_name='opaque-store',
        function_name='opaque_parser',
        append_branch='article_candidate',
        parser_path='opaque_path',
        caller_line_hint='contract-test',
        clean_label=lambda value: str(value or '').strip(),
        parse_quantity=lambda value: Decimal(str(value)) if value else None,
        parse_decimal=lambda value: Decimal(str(value)) if value else None,
        amount_to_float=lambda value: float(value) if value is not None else None,
        classify_line=lambda value: 'product_candidate',
        trace_line=lambda value: {
            'classification': 'product_candidate',
            'stage': 'contract_test',
            'rule': 'STRUCTURAL_ACCEPTANCE',
            'matched': None,
        },
    )
    assert index == 0
    assert len(extracted) == 1
    return extracted[0]


def test_accepted_product_candidate_has_product_line_type():
    line = _append()
    assert line['line_type'] == 'product'


def test_product_line_type_does_not_depend_on_label_or_store_text():
    first = _append('opaque-alpha')
    second = _append('completely-different-beta')
    assert first['line_type'] == second['line_type'] == 'product'
