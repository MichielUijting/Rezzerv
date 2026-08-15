from pathlib import Path

from app.receipt_ingestion.package_label_extraction import (
    apply_package_extraction_to_candidate,
    extract_package_from_label,
)
from app.receipt_ingestion.product_name_normalization import normalize_product_name_label


def test_single_package_becomes_one_purchased_unit_with_content():
    label, quantity, unit, metadata = apply_package_extraction_to_candidate('Lasagnebladen 500g')
    assert label == 'Lasagnebladen'
    assert quantity == 1
    assert unit == 'stuk'
    assert metadata['package_count'] == 1
    assert metadata['package_quantity'] == 500
    assert metadata['package_unit'] == 'g'


def test_purchase_count_is_not_overwritten_by_package_content():
    label, quantity, metadata = normalize_product_name_label('2 x Volkoren pasta 500g')
    assert label == 'Volkoren pasta 500g'
    assert quantity == 2
    label, quantity, unit, package = apply_package_extraction_to_candidate(label, quantity=quantity)
    assert label == 'Volkoren pasta'
    assert quantity == 2
    assert unit is None
    assert package['package_quantity'] == 500
    assert package['package_unit'] == 'g'


def test_trailing_purchase_count_is_removed_with_explicit_transaction_proof():
    label, quantity, metadata = normalize_product_name_label(
        'Fairtrade Chenin B1 2',
        transaction_text='Fairtrade Chenin B1 2 x 4,49 8,98 C',
    )
    assert label == 'Fairtrade Chenin B1'
    assert quantity == 2
    assert 'trailing_transaction_item_count_removed' in metadata['normalization_rules']


def test_trailing_purchase_count_is_removed_with_financial_proof_when_parser_already_split_multiplier():
    label, quantity, metadata = normalize_product_name_label(
        'Fairtrade Chenin B1 2',
        transaction_text='Fairtrade Chenin B1 2',
        unit_price='4,49',
        line_total='8,98',
    )
    assert label == 'Fairtrade Chenin B1'
    assert quantity == 2
    assert 'trailing_transaction_item_count_removed' in metadata['normalization_rules']


def test_trailing_product_numbers_are_preserved_without_matching_transaction_or_financial_proof():
    cases = (
        ('Vitamine B12', '4,99', '4,99'),
        ('iPhone 16', '4,99', '4,99'),
        ('Product model 2', '4,99', '4,99'),
        ('Chenin B1', '4,99', '4,99'),
    )
    for label, unit_price, line_total in cases:
        normalized, quantity, metadata = normalize_product_name_label(
            label,
            transaction_text=f'{label} 4,99',
            unit_price=unit_price,
            line_total=line_total,
        )
        assert normalized == label
        assert quantity is None
        assert metadata is None


def test_financial_proof_must_match_trailing_count_exactly():
    normalized, quantity, metadata = normalize_product_name_label(
        'Product model 2',
        transaction_text='Product model 2',
        unit_price='4,99',
        line_total='14,97',
    )
    assert normalized == 'Product model 2'
    assert quantity is None
    assert metadata is None


def test_multipack_is_structured_without_leaking_into_name():
    result = extract_package_from_label('Coca-Cola zero 4 x 1,5 liter')
    assert result['article_label'] == 'Coca-Cola zero'
    assert result['package_count'] == 4
    assert result['package_quantity'] == 1.5
    assert result['package_unit'] == 'l'


def test_variant_percent_and_technical_specs_are_not_package_content():
    assert extract_package_from_label('Creme fraiche 30%') is None
    assert extract_package_from_label('Goudse kaas 48+') is None
    assert extract_package_from_label('Powerbank 10000 mAh') is None
    assert extract_package_from_label('Schuurpapier K150') is None
    assert extract_package_from_label('Paneel 280x28x1,8 cm') is None


def test_kassa_to_unpack_uses_normalized_name_and_persists_package_fields():
    source = Path('backend/app/main.py').read_text(encoding='utf-8')
    assert 'COALESCE(corrected_raw_label, normalized_label, raw_label) AS article_name' in source
    assert "'article_name_raw': article_name" in source
    assert "'package_count': package_count" in source
    assert "'content_value': content_value" in source
    assert "'content_unit': content_unit" in source
    assert "'package_count': 'NUMERIC(12,3)'" in source
    assert 'purchase_line_additions' in source


def test_gateway_supplies_transaction_and_financial_context_to_product_name_normalization():
    source = Path('backend/app/receipt_ingestion/product_candidate_gateway.py').read_text(encoding='utf-8')
    assert 'transaction_text=normalized_line or raw_line' in source
    assert 'unit_price=unit_price' in source
    assert 'line_total=line_total' in source
