from __future__ import annotations

from typing import Any, Dict, List

from .contracts import FORBIDDEN_PRODUCT_TOKENS, MIN_CONFIDENCE


def apply_parser_augmentation_safety_gate(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    seen_product_amounts = set()

    for candidate in candidates:
        reasons = _validate_candidate(candidate, seen_product_amounts)
        if reasons:
            rejected.append(
                {
                    **candidate,
                    'rejection_reasons': reasons,
                }
            )
            continue

        key = (
            str(candidate.get('product_name') or '').strip().lower(),
            str(candidate.get('amount')),
        )
        seen_product_amounts.add(key)
        accepted.append(candidate)

    return {
        'accepted_augmented_rows': accepted,
        'rejected_candidates': rejected,
        'summary': {
            'candidate_count': len(candidates),
            'accepted_count': len(accepted),
            'rejected_count': len(rejected),
        },
    }


def _validate_candidate(candidate: Dict[str, Any], seen_product_amounts: set) -> List[str]:
    reasons: List[str] = []

    name = str(candidate.get('product_name') or '').strip()
    amount = candidate.get('amount')
    confidence = float(candidate.get('confidence') or 0.0)

    if not name:
        reasons.append('missing_product_name')

    if amount in (None, ''):
        reasons.append('missing_amount')
    else:
        try:
            numeric_amount = float(amount)
            if numeric_amount <= 0:
                reasons.append('amount_not_positive')
        except Exception:
            reasons.append('amount_not_numeric')

    if confidence < MIN_CONFIDENCE:
        reasons.append('confidence_below_threshold')

    lowered_name = name.lower()
    if any(token in lowered_name for token in FORBIDDEN_PRODUCT_TOKENS):
        reasons.append('forbidden_total_or_payment_rule')

    duplicate_key = (lowered_name, str(amount))
    if duplicate_key in seen_product_amounts:
        reasons.append('duplicate_product_amount_candidate')

    return reasons
