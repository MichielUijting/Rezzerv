from __future__ import annotations

from typing import Any, Dict, List


def build_parser_candidates(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build diagnostic-only parser candidates.

    This function NEVER mutates parser_rows. It only proposes possible rows
    that may later become eligible for controlled parser augmentation.
    """
    candidates: List[Dict[str, Any]] = []

    diagnostics = payload.get('diagnostics') or {}
    normalized = payload.get('normalized_review_diagnostics') or {}
    review_suggestions = payload.get('review_suggestions') or []

    parser_rows = payload.get('parser_rows') or []
    for row in parser_rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get('product_name') or row.get('name') or '').strip()
        amount = row.get('amount') or row.get('price')
        if not name or amount in (None, ''):
            continue
        candidates.append(
            {
                'product_name': name,
                'amount': amount,
                'source': 'existing_parser_row',
                'confidence': 0.98,
                'evidence': ['existing parser row'],
            }
        )

    for suggestion in review_suggestions:
        if not isinstance(suggestion, dict):
            continue
        name = str(suggestion.get('product_name') or suggestion.get('name') or '').strip()
        amount = suggestion.get('amount') or suggestion.get('price')
        if not name or amount in (None, ''):
            continue
        candidates.append(
            {
                'product_name': name,
                'amount': amount,
                'source': 'review_suggestion',
                'confidence': float(suggestion.get('confidence') or 0.86),
                'evidence': ['review suggestion', 'diagnostic-only candidate'],
            }
        )

    consensus_groups = normalized.get('consensus_groups') or []
    for group in consensus_groups:
        if not isinstance(group, dict):
            continue
        name = str(group.get('product_name') or group.get('name') or '').strip()
        amount = group.get('amount') or group.get('price')
        if not name or amount in (None, ''):
            continue
        candidates.append(
            {
                'product_name': name,
                'amount': amount,
                'source': 'consensus_group',
                'confidence': float(group.get('confidence') or 0.90),
                'evidence': ['cross-route OCR consensus'],
            }
        )

    shadow_candidates = diagnostics.get('shadow_reconstruction_candidates') or []
    for candidate in shadow_candidates:
        if not isinstance(candidate, dict):
            continue
        name = str(candidate.get('product_name') or candidate.get('name') or '').strip()
        amount = candidate.get('amount') or candidate.get('price')
        if not name or amount in (None, ''):
            continue
        candidates.append(
            {
                'product_name': name,
                'amount': amount,
                'source': 'shadow_reconstruction',
                'confidence': float(candidate.get('confidence') or 0.87),
                'evidence': ['weighted shadow reconstruction'],
            }
        )

    return candidates
