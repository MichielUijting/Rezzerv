from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services import receipt_loyalty_line_patch as loyalty
from app.services import receipt_parser_quality_patch as qpatch

STORE_KEYS = {"aldi", "lidl", "lidl nederland gmbh"}


def _store_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _label_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _dec(value: Any):
    return qpatch._parse_decimal(value)


def _qty_is_single_or_empty(value: Any) -> bool:
    parsed = _dec(value)
    return parsed is None or parsed == qpatch.Decimal("1.00")


def _source_is_adjacent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("source_index") is None or right.get("source_index") is None:
        return True
    try:
        return abs(int(right.get("source_index")) - int(left.get("source_index"))) <= 1
    except (TypeError, ValueError):
        return False


def _can_merge(left: dict[str, Any], right: dict[str, Any], store_name: Any) -> bool:
    store = _store_key(store_name)
    if store not in STORE_KEYS:
        return False
    if not _source_is_adjacent(left, right):
        return False
    if not _qty_is_single_or_empty(left.get("quantity")) or not _qty_is_single_or_empty(right.get("quantity")):
        return False

    left_total = _dec(left.get("line_total"))
    right_total = _dec(right.get("line_total"))
    if left_total is None or right_total is None:
        return False
    if left_total <= qpatch.Decimal("0.00") or left_total != right_total:
        return False

    left_key = _label_key(left.get("normalized_label") or left.get("raw_label"))
    right_key = _label_key(right.get("normalized_label") or right.get("raw_label"))
    if len(left_key) < 6 or len(right_key) < 6:
        return False

    if store.startswith("lidl"):
        return left_key == right_key

    similarity = SequenceMatcher(None, left_key, right_key).ratio()
    return similarity >= 0.92 and abs(len(left_key) - len(right_key)) <= 2


def _merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)

    left_total = _dec(left.get("line_total")) or qpatch.Decimal("0.00")
    right_total = _dec(right.get("line_total")) or qpatch.Decimal("0.00")
    merged["line_total"] = qpatch._as_float((left_total + right_total).quantize(qpatch.Decimal("0.01")))

    unit_price = _dec(left.get("unit_price")) or right_total
    merged["unit_price"] = qpatch._as_float(unit_price)
    merged["quantity"] = 2

    left_discount = _dec(left.get("discount_amount")) or qpatch.Decimal("0.00")
    right_discount = _dec(right.get("discount_amount")) or qpatch.Decimal("0.00")
    discount_total = (left_discount + right_discount).quantize(qpatch.Decimal("0.01"))
    merged["discount_amount"] = qpatch._as_float(discount_total) if discount_total != qpatch.Decimal("0.00") else None

    companion = str(right.get("normalized_label") or right.get("raw_label") or "").strip()
    merged["duplicate_merge_applied"] = True
    merged["merged_companion_label"] = companion
    merged["merged_companion_line_total"] = qpatch._as_float(right_total)
    merged["confidence_score"] = max(float(left.get("confidence_score") or 0), float(right.get("confidence_score") or 0), 0.86)
    return merged


def _merge_adjacent(lines: list[dict[str, Any]], store_name: Any = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and _can_merge(lines[i], lines[i + 1], store_name):
            result.append(_merge(lines[i], lines[i + 1]))
            i += 2
        else:
            result.append(lines[i])
            i += 1
    return result


_ORIGINAL_LOYALTY_NORMALIZE = loyalty._normalize_receipt_lines


def _normalize_receipt_lines(lines: list[dict[str, Any]] | None, store_name: Any = None) -> list[dict[str, Any]]:
    normalized = _ORIGINAL_LOYALTY_NORMALIZE(lines, store_name)
    return _merge_adjacent(normalized, store_name)


def install_receipt_g1_merge(*_: Any) -> bool:
    loyalty._normalize_receipt_lines = _normalize_receipt_lines
    qpatch._normalize_receipt_lines = _normalize_receipt_lines
    return True


install_receipt_g1_merge()
