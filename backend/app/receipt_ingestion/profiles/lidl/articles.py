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
"""Lidl article classification extension points for R9-38A0."""


from dataclasses import dataclass
from typing import Literal

LidlLineKind = Literal["unknown", "article", "non_product", "discount", "total", "payment", "tax", "metadata"]


@dataclass(frozen=True)
class LidlLineClassification:
    """Diagnostic-only Lidl line classification placeholder."""

    kind: LidlLineKind = "unknown"
    reason: str = "r9_38a0_skeleton"


def classify_lidl_line(line: str | None, *, context: object | None = None) -> LidlLineClassification:
    """Classify a Lidl line for future diagnostics.

    R9-38A0 does not make article decisions. It returns an unknown diagnostic
    classification only, leaving the active parser unchanged.
    """
    return LidlLineClassification()
