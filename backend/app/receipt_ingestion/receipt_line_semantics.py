"""Persistent business semantics for canonical receipt lines.

Hard architecture rule: receipt/article/store text is opaque data here. Business
routing must depend only on the scanner-provided canonical ``line_type`` (or an
already persisted business role), never on words found in a receipt label.
"""
from __future__ import annotations

from typing import Any

ROLE_PRODUCT = 'product'
ROLE_LOYALTY = 'loyalty'
ROLE_FINANCIAL = 'financial'
ROLE_METADATA = 'metadata'
ROLE_UNKNOWN = 'unknown'

_CANONICAL_TO_BUSINESS_ROLE: dict[str, tuple[str, bool]] = {
    'product': (ROLE_PRODUCT, True),
    'loyalty': (ROLE_LOYALTY, False),
    'discount': (ROLE_FINANCIAL, False),
    'deposit': (ROLE_FINANCIAL, False),
    'shipping': (ROLE_FINANCIAL, False),
    'fee': (ROLE_FINANCIAL, False),
    'subtotal': (ROLE_FINANCIAL, False),
    'total': (ROLE_FINANCIAL, False),
    'tax': (ROLE_FINANCIAL, False),
    'payment': (ROLE_FINANCIAL, False),
    'header': (ROLE_METADATA, False),
    'footer': (ROLE_METADATA, False),
    'noise': (ROLE_METADATA, False),
    'unknown': (ROLE_UNKNOWN, False),
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def derive_receipt_line_semantics(
    line: dict[str, Any],
    *,
    store_name: str | None = None,
) -> dict[str, Any]:
    """Map canonical scanner facts to persistent Rezzerv business semantics.

    ``store_name`` remains in the call signature for compatibility while callers
    are migrated; it is deliberately ignored. No receipt text is inspected.

    Unknown/untyped lines fail closed: they remain available for review but can
    never silently become physical inventory.
    """
    del store_name
    if not isinstance(line, dict):
        return {'line_role': ROLE_UNKNOWN, 'inventory_eligible': False}

    persisted_role = str(line.get('line_role') or '').strip().lower()
    persisted_eligible = line.get('inventory_eligible')
    if persisted_role and persisted_eligible is not None:
        return {
            'line_role': persisted_role,
            'inventory_eligible': _as_bool(persisted_eligible),
        }

    canonical_type = str(line.get('line_type') or '').strip().lower()
    role, eligible = _CANONICAL_TO_BUSINESS_ROLE.get(
        canonical_type,
        (ROLE_UNKNOWN, False),
    )
    return {'line_role': role, 'inventory_eligible': eligible}
