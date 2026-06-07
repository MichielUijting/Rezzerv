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

from .base import (
    ProfileDetection,
    ProfileDiagnostics,
    ProfileLineClassification,
    ProfileParseContext,
    ProfileHeaderResult,
    ProfileArticleResult,
    ReceiptStoreProfile,
    READ_ONLY_PROFILE_GUARDRAILS,
)

__all__ = [
    'ProfileDetection',
    'ProfileDiagnostics',
    'ProfileLineClassification',
    'ProfileParseContext',
    'ProfileHeaderResult',
    'ProfileArticleResult',
    'ReceiptStoreProfile',
    'READ_ONLY_PROFILE_GUARDRAILS',
]
