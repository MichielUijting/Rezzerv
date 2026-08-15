from pathlib import Path

import pytest

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics


@pytest.mark.parametrize(
    ('line_type', 'expected_role', 'eligible'),
    [
        ('product', 'product', True),
        ('loyalty', 'loyalty', False),
        ('discount', 'financial', False),
        ('deposit', 'financial', False),
        ('shipping', 'financial', False),
        ('fee', 'financial', False),
        ('tax', 'financial', False),
        ('payment', 'financial', False),
        ('total', 'financial', False),
        ('header', 'metadata', False),
        ('footer', 'metadata', False),
        ('noise', 'metadata', False),
        ('unknown', 'unknown', False),
    ],
)
def test_semantic_routing_depends_on_canonical_role_not_text(line_type, expected_role, eligible):
    labels = [
        'opaque-A 17',
        'λ 9 x 2,75',
        '任意文字列 500',
        '--- 123 ---',
    ]
    stores = ['source-A', 'source-B', '任意']
    for label in labels:
        for store in stores:
            result = derive_receipt_line_semantics(
                {
                    'line_type': line_type,
                    'raw_label': label,
                    'normalized_label': label[::-1],
                },
                store_name=store,
            )
            assert result == {
                'line_role': expected_role,
                'inventory_eligible': eligible,
            }


def test_untyped_line_fails_closed_independent_of_text():
    for label in ('opaque', '999,99', 'αβγ', 'x y z'):
        assert derive_receipt_line_semantics({'raw_label': label}) == {
            'line_role': 'unknown',
            'inventory_eligible': False,
        }


def test_semantic_core_has_no_receipt_text_classifier_dependency():
    source = Path('backend/app/receipt_ingestion/receipt_line_semantics.py').read_text(encoding='utf-8')
    forbidden = (
        'line_classifier',
        'spaarzegels_terms',
        'raw_label',
        'normalized_label',
        'corrected_raw_label',
        'trace_receipt_text_line_classification',
    )
    for token in forbidden:
        assert token not in source, token
