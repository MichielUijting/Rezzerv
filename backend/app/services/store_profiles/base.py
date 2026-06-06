"""
Technical Design Reference:
- TD Section: TD-05 Datastore en services
- Module Role: Backend application module
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
from dataclasses import dataclass

from app.services.receipt_line_classifier import (
    LINE_CATEGORY_DISCOUNT,
    LINE_CATEGORY_LOYALTY,
    classify_receipt_line,
    normalized_skip_text,
)


@dataclass(frozen=True)
class StoreProfile:
    """Read-only store parser profile.

    Store profiles may refine line classification for parsing and diagnostics.
    They must not determine PO status and must not decide whether a receipt is
    Gecontroleerd. That remains the responsibility of the baseline status
    service.
    """

    key: str
    display_name: str
    store_patterns: tuple[str, ...] = ()
    loyalty_patterns: tuple[str, ...] = ()
    discount_patterns: tuple[str, ...] = ()
    meta_patterns: tuple[str, ...] = ()

    def matches_store(self, store_name: str | None, filename: str | None = None) -> bool:
        haystack = f'{store_name or ""} {filename or ""}'.lower()
        return any(re.search(pattern, haystack, flags=re.IGNORECASE) for pattern in self.store_patterns)

    def classify_line(self, line: str) -> str:
        normalized = normalized_skip_text(line)
        if self._matches_any(normalized, self.loyalty_patterns):
            return LINE_CATEGORY_LOYALTY
        if self._matches_any(normalized, self.discount_patterns):
            return LINE_CATEGORY_DISCOUNT
        return classify_receipt_line(line)

    @staticmethod
    def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


GENERIC_PROFILE = StoreProfile(key='generic', display_name='Generic')


def get_store_profile(store_name: str | None = None, filename: str | None = None) -> StoreProfile:
    from app.services.store_profiles.ah import AH_PROFILE
    from app.services.store_profiles.aldi import ALDI_PROFILE
    from app.services.store_profiles.jumbo import JUMBO_PROFILE
    from app.services.store_profiles.lidl import LIDL_PROFILE
    from app.services.store_profiles.plus import PLUS_PROFILE

    for profile in (AH_PROFILE, JUMBO_PROFILE, LIDL_PROFILE, PLUS_PROFILE, ALDI_PROFILE):
        if profile.matches_store(store_name, filename):
            return profile
    return GENERIC_PROFILE


def classify_line_for_store(line: str, store_name: str | None = None, filename: str | None = None) -> str:
    return get_store_profile(store_name, filename).classify_line(line)
