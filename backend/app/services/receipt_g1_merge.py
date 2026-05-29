from __future__ import annotations

"""Deprecated receipt G1 merge monkeypatch.

R9-36N4:
This module is retained only for import compatibility. It must not mutate
``receipt_loyalty_line_patch`` or ``receipt_parser_quality_patch`` at import time.
Duplicate-line merge behaviour, if still required, must be implemented explicitly
inside the normal receipt parser flow and covered by parser regression tests.
"""

from typing import Any


def install_receipt_g1_merge(*_: Any) -> bool:
    """Compatibility no-op: do not patch parser helper modules."""
    return False
