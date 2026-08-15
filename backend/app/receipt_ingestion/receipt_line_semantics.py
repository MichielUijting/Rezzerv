"""Persistent semantic contract for logical receipt lines.

A receipt line is classified once at ingestion and that classification is stored
on receipt_table_lines. Downstream flows consume the stored decision instead of
reclassifying a display/raw string.
"""
from __future__ import annotations

from typing import Any
from app.receipt_ingestion.line_classifier import trace_receipt_text_line_classification
from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded

ROLE_PRODUCT = 'product'
ROLE_LOYALTY = 'loyalty'
ROLE_FINANCIAL = 'financial'
ROLE_METADATA = 'metadata'


def _semantic_text(line: dict[str, Any]) -> str:
    return str(
        line.get('corrected_raw_label')
        or line.get('normalized_label')
        or line.get('raw_label')
        or ''
    ).strip()


def _classification_trace(line: dict[str, Any], *, store_name: str | None = None) -> dict[str, Any]:
    producer = line.get('producer_trace')
    if isinstance(producer, dict):
        nested = producer.get('classification_trace')
        if isinstance(nested, dict) and nested.get('classification'):
            return dict(nested)
        if producer.get('classification'):
            return {
                'classification': producer.get('classification'),
                'rule': producer.get('classification_rule'),
                'matched': producer.get('classification_matched'),
                'stage': producer.get('classification_stage') or 'producer_trace',
            }
    label = _semantic_text(line)
    if not label:
        return {'classification': 'ignore', 'rule': 'EMPTY_OR_WHITESPACE_LINE', 'stage': 'semantic'}
    return trace_receipt_text_line_classification(label, store_name=store_name)


def derive_receipt_line_semantics(
    line: dict[str, Any],
    *,
    store_name: str | None = None,
) -> dict[str, Any]:
    """Return the persistent semantic role and inventory eligibility for one logical line."""
    if not isinstance(line, dict):
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}

    # Persisted semantics are authoritative once present.
    persisted_role = str(line.get('line_role') or '').strip()
    persisted_eligible = line.get('inventory_eligible')
    if persisted_role and persisted_eligible is not None:
        return {
            'line_role': persisted_role,
            'inventory_eligible': bool(int(persisted_eligible)) if isinstance(persisted_eligible, (int, str)) else bool(persisted_eligible),
        }

    semantic_context = dict(line)
    semantic_context.setdefault('receipt_line_text', _semantic_text(line))
    if is_spaarzegels_flow_excluded(semantic_context):
        return {'line_role': ROLE_LOYALTY, 'inventory_eligible': False}

    trace = _classification_trace(line, store_name=store_name)
    classification = str(trace.get('classification') or '')
    rule = str(trace.get('rule') or '')

    if classification == 'product_candidate':
        # Savings/action value rows may deliberately pass the product-candidate
        # gateway for financial accounting, but never become physical stock.
        if rule in {
            'GENERIC_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
            'PLUS_PRICED_DISCOUNT_OR_SPAARZEGELS_LINE',
            'GENERIC_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
            'STORE_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION',
        }:
            return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
        return {'line_role': ROLE_PRODUCT, 'inventory_eligible': True}

    if classification == 'footer_payment_tax':
        return {'line_role': ROLE_FINANCIAL, 'inventory_eligible': False}
    if classification in {'metadata', 'amount_detail', 'continuation'}:
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
    if classification == 'ignore' and rule != 'NO_RULE_MATCHED':
        return {'line_role': ROLE_METADATA, 'inventory_eligible': False}
    # receipt_table_lines already contains logical parsed receipt candidates.
    # If no explicit non-inventory rule matched, fail open to a physical product
    # so unknown/new article wording is never silently lost from Uitpakken.
    return {'line_role': ROLE_PRODUCT, 'inventory_eligible': True}
