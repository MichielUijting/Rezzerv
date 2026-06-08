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
"""Profile-only receipt total router.

R9-36C architecture rule:
receipt.total_amount may only come from an explicit store profile total extractor.
There is no generic total fallback and no article-line-sum fallback.
"""


from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from app.receipt_ingestion.profiles.ah.detect import looks_like_ah_context
from app.receipt_ingestion.profiles.ah.diagnostics import build_ah_total_diagnostics
from app.receipt_ingestion.profiles.ah.totals import AhTotalResult, extract_ah_total_amount


@dataclass(frozen=True)
class ProfileTotalResolution:
    amount: Decimal | None
    explicit_total_found: bool
    source: str
    profile: str | None
    diagnostics: dict[str, Any]


def _none_resolution(reason: str) -> ProfileTotalResolution:
    return ProfileTotalResolution(
        amount=None,
        explicit_total_found=False,
        source='none',
        profile=None,
        diagnostics={
            'total_resolution': {
                'source': 'none',
                'profile': None,
                'amount': None,
                'explicit_total_found': False,
                'reason': reason,
            }
        },
    )


def _ah_resolution(result: AhTotalResult, source_lines_count: int) -> ProfileTotalResolution:
    ah_diagnostics = build_ah_total_diagnostics(result)
    return ProfileTotalResolution(
        amount=result.amount,
        explicit_total_found=result.explicit_total_found,
        source='profile',
        profile='ah',
        diagnostics={
            'total_resolution': {
                'source': 'profile',
                'profile': 'ah',
                'amount': str(result.amount) if result.amount is not None else None,
                'explicit_total_found': result.explicit_total_found,
                'source_lines_count': source_lines_count,
            },
            'ah_total': ah_diagnostics,
        },
    )


def resolve_profile_total_amount(
    text_lines: Iterable[object] | None,
    filename: str | None = None,
    *,
    store_name: str | None = None,
) -> ProfileTotalResolution:
    """Resolve receipt total using store profiles only.

    For now, only the AH total profile is active. All non-AH receipts return
    amount=None by design so hidden generic total algorithms cannot mask errors.
    """
    source_lines = list(text_lines or [])
    if looks_like_ah_context(source_lines, filename, store_name=store_name):
        return _ah_resolution(
            extract_ah_total_amount(source_lines, filename, store_name=store_name),
            source_lines_count=len(source_lines),
        )
    return _none_resolution('no_profile_total_available')
