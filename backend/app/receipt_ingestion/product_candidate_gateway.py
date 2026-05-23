from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.receipt_ingestion.line_classifier import classification_allows_append


CleanLabel = Callable[[str | None], str]
ParseQuantity = Callable[[str | None], Any]
ParseDecimal = Callable[[str | None], Any]
AmountToFloat = Callable[[Any], float | None]
ClassifyLine = Callable[[str], str]
TraceLine = Callable[[str], dict[str, Any]]
InvalidLabelCheck = Callable[[str], bool]


def append_product_candidate(
    extracted: list[dict[str, Any]],
    *,
    label: str | None,
    qty_raw: str | None,
    amount1_raw: str | None,
    amount2_raw: str | None,
    source_index: int,
    raw_line: str | None,
    normalized_line: str | None,
    filename: str | None,
    store_name: str | None,
    function_name: str,
    append_branch: str,
    parser_path: str,
    caller_line_hint: str,
    clean_label: CleanLabel,
    parse_quantity: ParseQuantity,
    parse_decimal: ParseDecimal,
    amount_to_float: AmountToFloat,
    classify_line: ClassifyLine,
    trace_line: TraceLine | None = None,
    is_invalid_label: InvalidLabelCheck | None = None,
    confidence_score: float = 0.85,
) -> int | None:
    """Single guarded gateway for appending receipt product candidates.

    The gateway is intentionally parser-status neutral: it only decides whether a
    parsed line may become a product candidate. Receipt status remains outside
    receipt ingestion and must stay with the SSOT status service.
    """
    label_value = clean_label(label)
    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None
    if is_invalid_label is not None and is_invalid_label(label_value):
        return None

    classification_trace = trace_line(label_value) if trace_line is not None else None
    classification = str((classification_trace or {}).get('classification') or classify_line(label_value))
    append_allowed = classification_allows_append(classification)
    if not append_allowed:
        return None

    quantity = parse_quantity((qty_raw or '').replace('kg', '').replace('KG', '').strip()) if qty_raw else None
    try:
        if quantity is not None and quantity <= 0:
            quantity = None
    except TypeError:
        quantity = None

    amount1 = parse_decimal(amount1_raw)
    amount2 = parse_decimal(amount2_raw)
    if amount1 is None and amount2 is None:
        return None

    if amount2 is not None:
        unit_price = amount1
        line_total = amount2
    else:
        unit_price = amount1
        line_total = amount1

    producer_trace = {
        'filename': filename,
        'store_name': store_name,
        'function_name': function_name,
        'append_branch': append_branch,
        'parser_path': parser_path,
        'source_index': source_index,
        'raw_line': raw_line,
        'normalized_line': normalized_line,
        'label': label_value,
        'amount': amount_to_float(line_total),
        'classification': classification,
        'classification_allows_append': append_allowed,
        'append_allowed': append_allowed,
        'caller_line_hint': caller_line_hint,
    }
    if classification_trace:
        producer_trace.update({
            'classification_rule': classification_trace.get('rule'),
            'classification_stage': classification_trace.get('stage'),
            'classification_matched': classification_trace.get('matched'),
            'classification_trace': classification_trace,
        })

    extracted.append(
        {
            'raw_label': label_value,
            'normalized_label': label_value,
            'quantity': amount_to_float(quantity),
            'unit': 'kg' if qty_raw and 'kg' in qty_raw.lower() else None,
            'unit_price': amount_to_float(unit_price),
            'line_total': amount_to_float(line_total),
            'discount_amount': None,
            'barcode': None,
            'confidence_score': confidence_score,
            'source_index': source_index,
            'producer_trace': producer_trace,
        }
    )
    return len(extracted) - 1
