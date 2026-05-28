"""Albert Heijn detection profile.

Small, conservative AH profile boundary for R9-36B.
This module detects whether source lines belong to Albert Heijn.
It must not parse articles, store branches, status, or totals.
"""

from __future__ import annotations

import re
from typing import Iterable


_AH_STORE_NAMES = {'albert heijn'}
_AH_SOURCE_MARKERS = (
    'albert heijn',
    'ah.nl',
    'ah to go',
)


def _normalize(value: object) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip().lower()


def looks_like_ah_context(
    text_lines: Iterable[object] | None,
    filename: str | None = None,
    *,
    store_name: str | None = None,
) -> bool:
    """Return True only for a conservative Albert Heijn context.

    Detection is intentionally narrow:
    - an already parsed store_name of exactly "Albert Heijn" is accepted;
    - otherwise the first source lines or filename must contain a clear AH marker.

    A loose standalone "AH" token is not enough, to avoid accidental matches.
    """
    normalized_store = _normalize(store_name)
    if normalized_store in _AH_STORE_NAMES:
        return True

    first_lines = list(text_lines or [])[:25]
    haystack = _normalize(' '.join(str(line or '') for line in first_lines))
    filename_text = _normalize(filename)
    combined = f'{haystack} {filename_text}'.strip()
    if not combined:
        return False

    return any(marker in combined for marker in _AH_SOURCE_MARKERS)
