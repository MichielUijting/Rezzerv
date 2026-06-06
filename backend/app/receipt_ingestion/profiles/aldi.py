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

import re
from typing import Any


def is_aldi_context(store_name: str | None = None, filename: str | None = None) -> bool:
    value = f'{store_name or ""} {filename or ""}'.lower()
    return 'aldi' in value


def is_aldi_opening_hours_line(line: str | None) -> bool:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip().upper().replace(',', '.')
    if not normalized:
        return False
    if re.fullmatch(r'(?:MA|DI|WO|DO|VR|ZA|ZO|ZON)\s+\d{1,2}\.\d{2}', normalized):
        return True
    if re.fullmatch(r'\d{1,2}\s+\d{1,2}\.\d{2}', normalized):
        return True
    return False


def is_aldi_non_product_line(line: str | None) -> bool:
    return is_aldi_opening_hours_line(line)


def filter_aldi_duplicate_lines(
    lines: list[dict[str, Any]],
    *,
    store_name: str | None = None,
    filename: str | None = None,
) -> list[dict[str, Any]]:
    return list(lines or [])
