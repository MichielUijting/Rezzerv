"""Lidl header parsing extension points for R9-38A0."""

from __future__ import annotations


def parse_lidl_header(lines: list[str] | tuple[str, ...] | None) -> dict[str, object]:
    """Return Lidl header metadata placeholder.

    R9-38A0 is structure-only and returns no extracted metadata yet.
    """
    return {}
