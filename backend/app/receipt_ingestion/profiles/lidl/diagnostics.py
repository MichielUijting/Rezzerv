"""Lidl diagnostics extension points for R9-38A0."""

from __future__ import annotations


def build_lidl_diagnostics(lines: list[str] | tuple[str, ...] | None) -> dict[str, object]:
    """Return Lidl diagnostics placeholder.

    R9-38A0 adds only a stable diagnostics surface.
    """
    return {"profile": "lidl", "stage": "r9_38a0_skeleton"}
