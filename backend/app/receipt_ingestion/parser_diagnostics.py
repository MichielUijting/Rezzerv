"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ParserDiagnosticEvent:
    """Normalized diagnostic event derived from a receipt producer_trace.

    This module is deliberately side-effect free. It does not decide receipt
    status, does not filter candidates and does not mutate parser output.
    """

    parser_path: str | None = None
    append_branch: str | None = None
    classification: str | None = None
    classification_rule: str | None = None
    classification_stage: str | None = None
    classification_matched: str | None = None
    classification_trace: dict[str, Any] | None = None
    append_allowed: bool | None = None
    blocked_reason: str | None = None
    source_index: int | None = None
    raw_line: str | None = None
    normalized_line: str | None = None
    source_segment: str | None = None
    label: str | None = None
    amount: float | None = None
    filename: str | None = None
    store_name: str | None = None
    function_name: str | None = None
    caller_line_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {'true', '1', 'yes', 'y'}:
        return True
    if normalized in {'false', '0', 'no', 'n'}:
        return False
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_trace(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    return None


def normalize_producer_trace(trace: dict[str, Any] | None) -> ParserDiagnosticEvent:
    """Convert a raw producer_trace dict to the stable diagnostic shape."""
    raw = trace or {}
    append_allowed = _coerce_bool(raw.get('append_allowed'))
    classification_allows_append = _coerce_bool(raw.get('classification_allows_append'))
    blocked_reason = raw.get('blocked_reason')
    if blocked_reason is None and append_allowed is False:
        blocked_reason = 'append_not_allowed'
    if blocked_reason is None and classification_allows_append is False:
        blocked_reason = 'classification_blocked'

    return ParserDiagnosticEvent(
        parser_path=raw.get('parser_path'),
        append_branch=raw.get('append_branch'),
        classification=raw.get('classification'),
        classification_rule=raw.get('classification_rule'),
        classification_stage=raw.get('classification_stage'),
        classification_matched=raw.get('classification_matched'),
        classification_trace=_coerce_trace(raw.get('classification_trace')),
        append_allowed=append_allowed,
        blocked_reason=blocked_reason,
        source_index=_coerce_int(raw.get('source_index')),
        raw_line=raw.get('raw_line'),
        normalized_line=raw.get('normalized_line'),
        source_segment=raw.get('source_segment'),
        label=raw.get('label'),
        amount=_coerce_float(raw.get('amount')),
        filename=raw.get('filename'),
        store_name=raw.get('store_name'),
        function_name=raw.get('function_name'),
        caller_line_hint=raw.get('caller_line_hint'),
    )


def diagnostic_events_from_lines(lines: list[dict[str, Any]] | None) -> list[ParserDiagnosticEvent]:
    """Extract normalized diagnostic events from parsed receipt lines."""
    events: list[ParserDiagnosticEvent] = []
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        trace = line.get('producer_trace')
        if isinstance(trace, dict):
            events.append(normalize_producer_trace(trace))
    return events


def summarize_parser_diagnostics(events: list[ParserDiagnosticEvent] | None) -> dict[str, Any]:
    """Build a compact parser-run summary from normalized events."""
    normalized_events = list(events or [])
    by_branch = Counter(event.append_branch or 'unknown' for event in normalized_events)
    by_classification = Counter(event.classification or 'unknown' for event in normalized_events)
    by_classification_rule = Counter(event.classification_rule or 'unknown' for event in normalized_events)
    by_classification_stage = Counter(event.classification_stage or 'unknown' for event in normalized_events)
    by_blocked_reason = Counter(event.blocked_reason or 'none' for event in normalized_events)
    appended_candidates = sum(1 for event in normalized_events if event.append_allowed is True)
    blocked_candidates = sum(1 for event in normalized_events if event.append_allowed is False)
    return {
        'total_candidates': len(normalized_events),
        'appended_candidates': appended_candidates,
        'blocked_candidates': blocked_candidates,
        'by_branch': dict(sorted(by_branch.items())),
        'by_classification': dict(sorted(by_classification.items())),
        'by_classification_rule': dict(sorted(by_classification_rule.items())),
        'by_classification_stage': dict(sorted(by_classification_stage.items())),
        'by_blocked_reason': dict(sorted(by_blocked_reason.items())),
    }


def summarize_lines_parser_diagnostics(lines: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Convenience wrapper for parser-run summary directly from receipt lines."""
    return summarize_parser_diagnostics(diagnostic_events_from_lines(lines))
