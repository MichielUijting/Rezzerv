"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: no
- Writes Data: no
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.receipt_ingestion.duplicate_lines import is_near_duplicate_of_previous
from app.receipt_ingestion.line_classifier import classification_allows_append
from app.receipt_ingestion.package_label_extraction import apply_package_extraction_to_candidate
from app.receipt_ingestion.product_name_normalization import normalize_product_name_label
from app.receipt_ingestion.spaarzegels_terms import spaarzegels_financial_metadata


CleanLabel = Callable[[str | None], str]
ParseQuantity = Callable[[str | None], Any]
ParseDecimal = Callable[[str | None], Any]
AmountToFloat = Callable[[Any], float | None]
ClassifyLine = Callable[[str], str]
TraceLine = Callable[[str], dict[str, Any]]
InvalidLabelCheck = Callable[[str], bool]


def _is_validated_savings_action_path(function_name: str, append_branch: str) -> bool:
    """Return True only for the existing savings/action value-line parser path."""
    return function_name == '_extract_savings_action_lines' and append_branch == 'savings_action_line'


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _consolidate_with_previous(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_total = _as_float(previous.get('line_total'))
    current_total = _as_float(current.get('line_total'))
    if previous_total is not None and current_total is not None:
        previous['line_total'] = round(previous_total + current_total, 2)
    previous_quantity = _as_float(previous.get('quantity'))
    current_quantity = _as_float(current.get('quantity'))
    if previous_quantity is not None or current_quantity is not None:
        previous['quantity'] = round((previous_quantity or 1.0) + (current_quantity or 1.0), 3)
    else:
        previous['quantity'] = 2.0
    trace = previous.get('producer_trace')
    if isinstance(trace, dict):
        trace['near_duplicate_consolidated'] = True
        trace['near_duplicate_consolidated_label'] = current.get('normalized_label') or current.get('raw_label')
        trace['near_duplicate_consolidated_amount'] = current_total


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
    """Single guarded gateway for appending receipt financial/product lines."""
    label_value = clean_label(label)
    if not label_value or len(label_value) < 2 or label_value.replace(' ', '').isdigit():
        return None

    savings_action_path = _is_validated_savings_action_path(function_name, append_branch)
    if is_invalid_label is not None and is_invalid_label(label_value) and not savings_action_path:
        return None

    classification_trace = trace_line(label_value) if trace_line is not None else None
    classification = str((classification_trace or {}).get('classification') or classify_line(label_value))
    classification_allowed = classification_allows_append(classification)
    append_allowed = classification_allowed or savings_action_path
    if not append_allowed:
        return None

    if not classification_trace:
        classification_trace = {
            'classification': classification,
            'stage': 'runtime_gateway',
            'rule': 'CLASSIFY_LINE_CALLBACK',
            'matched': label_value,
        }

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

    raw_label_value = clean_label(raw_line) if savings_action_path and raw_line else label_value
    label_value, quantity, unit_value, package_metadata = apply_package_extraction_to_candidate(
        label_value,
        quantity=quantity,
        unit='kg' if qty_raw and 'kg' in qty_raw.lower() else None,
    )
    label_value, quantity, name_metadata = normalize_product_name_label(label_value, quantity=quantity)
    raw_label_value = raw_label_value or label_value
    line_total_float = amount_to_float(line_total)
    financial_metadata = spaarzegels_financial_metadata(
        raw_label_value or label_value,
        label_text=label_value,
        detail_text=raw_label_value or normalized_line or raw_line,
    )

    candidate_line = {
        'raw_label': raw_label_value,
        'normalized_label': label_value,
        'quantity': amount_to_float(quantity),
        'unit': unit_value,
        'unit_price': amount_to_float(unit_price),
        'line_total': line_total_float,
        'discount_amount': None,
        'barcode': None,
        'confidence_score': confidence_score,
        'source_index': source_index,
    }
    if financial_metadata:
        candidate_line.update(financial_metadata)

    if extracted and is_near_duplicate_of_previous(candidate_line, extracted[-1]):
        _consolidate_with_previous(extracted[-1], candidate_line)
        return len(extracted) - 1

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
        'raw_label': raw_label_value,
        'amount': line_total_float,
        'classification': classification,
        'classification_allows_append': classification_allowed,
        'append_allowed': append_allowed,
        'caller_line_hint': caller_line_hint,
        'classification_rule': classification_trace.get('rule'),
        'classification_stage': classification_trace.get('stage'),
        'classification_matched': classification_trace.get('matched'),
        'classification_trace': classification_trace,
        'validated_savings_action_path': savings_action_path,
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
    if financial_metadata:
        producer_trace.update({
            'line_type': financial_metadata.get('line_type'),
            'is_spaarzegels': True,
            'include_in_receipt_total': True,
            'exclude_from_inventory': True,
            'external_matching_allowed': False,
            'matched_spaarzegels_term': financial_metadata.get('matched_spaarzegels_term'),
        })

    candidate_line['producer_trace'] = producer_trace
    extracted.append(candidate_line)
    return len(extracted) - 1
