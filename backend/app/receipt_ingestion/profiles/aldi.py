from __future__ import annotations

from typing import Any


def is_aldi_context(store_name: str | None = None, filename: str | None = None) -> bool:
    value = f'{store_name or ""} {filename or ""}'.lower()
    return 'aldi' in value


def is_aldi_non_product_line(line: str | None) -> bool:
    return False


def filter_aldi_duplicate_lines(
    lines: list[dict[str, Any]],
    *,
    store_name: str | None = None,
    filename: str | None = None,
) -> list[dict[str, Any]]:
    return list(lines or [])
