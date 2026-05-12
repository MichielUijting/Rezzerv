from __future__ import annotations

import re
from typing import Any

from app.services import receipt_parser_quality_patch as qpatch


def _line_key(line: dict[str, Any]) -> tuple[str, str, str]:
    label = re.sub(
        r'\s+',
        ' ',
        str(line.get('normalized_label') or line.get('raw_label') or '').strip().lower(),
    )
    return (
        label,
        str(line.get('line_total') or ''),
        str(line.get('source_index') or ''),
    )


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None, store_name: Any = None) -> list[dict[str, Any]]:
    """Compatibility shim for receipt_g1_merge without recursive monkeypatch calls.

    The previous shim delegated to qpatch._normalize_receipt_lines(), but
    receipt_g1_merge replaces that qpatch function with a wrapper that calls
    this function again. This standalone implementation deliberately performs
    only the minimal stable normalization needed by downstream merge logic:
    keep lines with a line_total, copy dictionaries, and de-duplicate.
    It does not add loyalty-line behavior and does not determine PO status.
    """
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        if line.get('line_total') is None:
            continue
        cleaned = dict(line)
        key = _line_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _reclassify_result(result: Any) -> Any:
    return qpatch._reclassify_result(result)


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    """Safety rollback: keep the module importable without monkeypatching parser behavior."""
    return True


install_receipt_loyalty_line_patch()
