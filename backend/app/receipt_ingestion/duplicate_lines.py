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

from difflib import SequenceMatcher
import re
from typing import Any


def _label_key(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _has_letters(value: str) -> bool:
    return bool(re.search(r'[a-z]', value))


def _amount_key(value: Any) -> str:
    if value is None:
        return ''
    try:
        return f'{float(value):.2f}'
    except (TypeError, ValueError):
        return str(value)


def _source_is_near(left: Any, right: Any, *, max_distance: int = 3) -> bool:
    if left is None or right is None:
        return False
    try:
        return abs(int(left) - int(right)) <= max_distance
    except (TypeError, ValueError):
        return False


def _line_label(line: dict[str, Any]) -> str:
    return str(line.get('normalized_label') or line.get('raw_label') or '')


def is_near_duplicate_of_previous(candidate: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    if not previous:
        return False
    candidate_key = _label_key(_line_label(candidate))
    previous_key = _label_key(_line_label(previous))
    if len(candidate_key) < 8 or len(previous_key) < 8:
        return False
    if not _has_letters(candidate_key) or not _has_letters(previous_key):
        return False
    if abs(len(candidate_key) - len(previous_key)) > 2:
        return False
    if _amount_key(candidate.get('line_total')) != _amount_key(previous.get('line_total')):
        return False
    if not _source_is_near(candidate.get('source_index'), previous.get('source_index')):
        return False
    return SequenceMatcher(None, candidate_key, previous_key).ratio() >= 0.92


def filter_near_duplicate_product_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for line in list(lines or []):
        if filtered and is_near_duplicate_of_previous(line, filtered[-1]):
            continue
        filtered.append(line)
    return filtered
