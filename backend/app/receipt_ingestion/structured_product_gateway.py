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

from collections.abc import Callable
from typing import Any

from app.receipt_ingestion.package_label_extraction import apply_package_extraction_to_candidate
from app.receipt_ingestion.product_name_normalization import normalize_product_name_label


CleanLabel = Callable[[str | None], str]
AmountToFloat = Callable[[Any], float | None]
InvalidLabelCheck = Callable[[str], bool]


def append_structured_product_candidate(
    extracted: list[dict[str, Any]],
    *,
    label: str | None,
    quantity: Any = None,
    unit: str | None = None,
    unit_price: Any = None,
    line_total: Any = None,
    discount_amount: Any = None,
    barcode: str | None = None,
    source_index: int | None = None,
    raw_line: str | None = None,
    normalized_line: str | None = None,
    source_segment: str | None = None,
    filename: str | None = None,
    store_name: str | None = None,
    function_name: str,
    append_branch: str,
    parser_path: str,
    caller_line_hint: str,
    clean_label: CleanLabel,
    amount_to_float: AmountToFloat,
    is_invalid_label: InvalidLabelCheck | None = None,
    confidence_score: float = 0.85,
) -> int | None:
    """Append a product candidate parsed from a structured source."""
    label_value = clean_label(label)
    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None

    is_picnic_structured_source = str(store_name or '').strip().lower() == 'picnic'
    if is_invalid_label is not None and not is_picnic_structured_source and is_invalid_label(label_value):
        return None

    if unit_price is None and line_total is None:
        return None

    label_value, quantity, unit, package_metadata = apply_package_extraction_to_candidate(
        label_value,
        quantity=quantity,
        unit=unit,
    )
    label_value, quantity, name_metadata = normalize_product_name_label(label_value, quantity=quantity)

    append_allowed = True
    producer_trace = {
        'filename': filename,
        'store_name': store_name,
        'function_name': function_name,
        'append_branch': append_branch,
        'parser_path': parser_path,
        'source_index': source_index,
        'raw_line': raw_line,
        'normalized_line': normalized_line,
        'source_segment': source_segment,
        'label': label_value,
        'amount': amount_to_float(line_total),
        'classification': 'structured_product_candidate',
        'classification_allows_append': append_allowed,
        'append_allowed': append_allowed,
        'caller_line_hint': caller_line_hint,
    }
    if package_metadata:
        producer_trace.update({
            'package_extraction_applied': True,
            'package_text': package_metadata.get('package_text'),
            'package_quantity': package_metadata.get('package_quantity'),
            'package_unit': package_metadata.get('package_unit'),
        })
    if name_metadata:
        producer_trace.update({
            'product_name_normalization_applied': True,
            'product_name_original_label': name_metadata.get('original_label'),
            'product_name_normalized_label': name_metadata.get('normalized_label'),
            'product_name_normalization_rules': name_metadata.get('normalization_rules'),
        })

    extracted.append(
        {
            'raw_label': label_value,
            'normalized_label': label_value,
            'quantity': amount_to_float(quantity),
            'unit': unit,
            'unit_price': amount_to_float(unit_price),
            'line_total': amount_to_float(line_total),
            'discount_amount': amount_to_float(discount_amount),
            'barcode': barcode,
            'confidence_score': confidence_score,
            'source_index': source_index,
            'producer_trace': producer_trace,
        }
    )
    return len(extracted) - 1
