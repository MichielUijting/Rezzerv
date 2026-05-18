from __future__ import annotations

from collections.abc import Callable
from typing import Any


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
    """Append a product candidate parsed from a structured source.

    This gateway is for store-specific PDF/e-mail parsers. Those parsers often
    derive a product from structured or semi-structured source fragments rather
    than from one OCR text line. For that reason this contract does not apply the
    OCR line-classifier, but it still enforces a uniform product shape and
    producer_trace.

    Receipt status remains outside receipt ingestion and must stay with the SSOT
    status service.
    """
    label_value = clean_label(label)
    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None
    if is_invalid_label is not None and is_invalid_label(label_value):
        return None
    if unit_price is None and line_total is None:
        return None

    append_allowed = True
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
            'producer_trace': {
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
            },
        }
    )
    return len(extracted) - 1
