from __future__ import annotations

from typing import Any

from app.services import receipt_parser_quality_patch as qpatch


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None, store_name: Any = None) -> list[dict[str, Any]]:
    """Compatibility shim for modules that still depend on the loyalty patch API.

    This function intentionally delegates to the stable parser quality patch and
    does not add loyalty-line behavior. It prevents startup/import crashes while
    keeping Receipt status governed by receipt_status_baseline_service_v4.py.
    """
    return qpatch._normalize_receipt_lines(lines or [])


def _reclassify_result(result: Any) -> Any:
    return qpatch._reclassify_result(result)


def install_receipt_loyalty_line_patch(*_: Any) -> bool:
    """Safety rollback: keep the module importable without monkeypatching parser behavior."""
    return True


install_receipt_loyalty_line_patch()
