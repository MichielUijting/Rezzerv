"""Lidl totals parsing extension points for R9-38A0."""

from __future__ import annotations


def parse_lidl_totals(lines: list[str] | tuple[str, ...] | None) -> dict[str, object]:
    """Return Lidl totals metadata placeholder.

    R9-38A0 does not extract or override totals.
    """
    return {}
