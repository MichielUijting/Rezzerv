from app.receipt_ingestion.package_label_extraction import apply_package_extraction_to_candidate, extract_package_from_label


def test_extracts_compact_gram_package_from_label():
    result = extract_package_from_label('Lasagnebladen 500g')

    assert result == {
        'article_label': 'Lasagnebladen',
        'package_quantity': 500,
        'package_unit': 'g',
        'package_text': '500g',
    }


def test_extracts_decimal_liter_package_from_label():
    label, quantity, unit, metadata = apply_package_extraction_to_candidate('Halfvolle Melk 1.0 L')

    assert label == 'Halfvolle Melk'
    assert quantity == 1
    assert unit == 'l'
    assert metadata == {
        'article_label': 'Halfvolle Melk',
        'package_quantity': 1,
        'package_unit': 'l',
        'package_text': '1.0 L',
    }


def test_does_not_override_existing_unit():
    label, quantity, unit, metadata = apply_package_extraction_to_candidate('Aardappel zoet', quantity=1.224, unit='kg')

    assert label == 'Aardappel zoet'
    assert quantity == 1.224
    assert unit == 'kg'
    assert metadata is None


def test_returns_none_for_label_without_package():
    assert extract_package_from_label('PREI') is None
