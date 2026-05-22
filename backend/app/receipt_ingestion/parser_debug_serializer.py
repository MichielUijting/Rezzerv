from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.receipt_ingestion.explainability import build_receipt_explainability

from app.receipt_ingestion.parser_diagnostics import (
    diagnostic_events_from_lines,
    summarize_lines_parser_diagnostics,
)


def group_events_by_branch(events: list[dict[str, Any]] | None) -> dict[str, dict[str, int]]:
    """Aggregate normalized diagnostic events by append branch."""
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {'count': 0, 'blocked': 0})

    for event in events or []:
        if not isinstance(event, dict):
            continue
        branch = str(event.get('append_branch') or 'unknown')
        grouped[branch]['count'] += 1
        if event.get('append_allowed') is False:
            grouped[branch]['blocked'] += 1

    return dict(sorted(grouped.items()))



def _safe_metadata(result: Any) -> dict[str, Any]:
    return {
        'store_name': getattr(result, 'store_name', None),
        'parse_status': getattr(result, 'parse_status', None),
        'confidence_score': getattr(result, 'confidence_score', None),
        'purchase_at': getattr(result, 'purchase_at', None),
        'total_amount': getattr(result, 'total_amount', None),
        'currency': getattr(result, 'currency', None),
    }



def build_parser_debug_payload(result: Any) -> dict[str, Any]:
    """Build a safe debug/review payload from a ReceiptParseResult-like object.

    This serializer is intentionally read-only and side-effect free.
    It must never mutate parser output or affect receipt status logic.
    """

    lines = getattr(result, 'lines', None) or []

    normalized_events = [
        event.to_dict()
        for event in diagnostic_events_from_lines(lines)
    ]

    summary = getattr(result, 'parser_diagnostics', None)
    if not isinstance(summary, dict):
        summary = summarize_lines_parser_diagnostics(lines)

    return {
        'summary': {
            'total_candidates': summary.get('total_candidates', 0),
            'appended_candidates': summary.get('appended_candidates', 0),
            'blocked_candidates': summary.get('blocked_candidates', 0),
            'by_classification': dict(summary.get('by_classification', {})),
            'by_blocked_reason': dict(summary.get('by_blocked_reason', {})),
        },
        'events': normalized_events,
        'branches': group_events_by_branch(normalized_events),
        'metadata': _safe_metadata(result),
        'explainability': build_receipt_explainability(result),
    }
