from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Callable

JUMBO_APP_QUANTITY_DETAIL_RE = re.compile(
    r"^\s*(?P<qty>\d+(?:[\.,]\d+)?)\s*[xX]\s*(?P<amount1>-?\d{1,6}(?:[\.,]\d{2}))"
    r"(?:\s+(?P<amount2>-?\d{1,6}(?:[\.,]\d{2})))?(?:\s+(?:EUR|[A-Z]{1,3}))?\s*$",
    re.IGNORECASE,
)

_JUMBO_NON_PRODUCT_LABEL_TOKENS = (
    "koopzegel",
    "koopzegels",
    "zegel",
    "zegels",
    "punten",
    "saldo",
    "totaal",
    "btw",
    "korting",
    "bankpas",
    "betaling",
)


def is_jumbo_context(store_name: str | None = None, filename: str | None = None) -> bool:
    haystack = f"{store_name or ''} {filename or ''}".lower()
    return "jumbo" in haystack


def normalize_jumbo_app_label(value: str | None) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    normalized = re.sub(r"^[^A-Za-z0-9À-ÖØ-öø-ÿ]+", "", normalized).strip()
    normalized = re.sub(r"[^A-Za-z0-9À-ÖØ-öø-ÿ]+$", "", normalized).strip()
    return normalized


def looks_like_safe_jumbo_app_pair_label(
    value: str | None,
    *,
    looks_like_non_product_receipt_label: Callable[[str], bool] | None = None,
) -> bool:
    label = normalize_jumbo_app_label(value)
    if len(label) < 3:
        return False
    lowered = label.lower()
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
        return False
    if re.search(r"\d{1,6}[\.,]\d{2}", label):
        return False
    if JUMBO_APP_QUANTITY_DETAIL_RE.match(label):
        return False
    if any(token in lowered for token in _JUMBO_NON_PRODUCT_LABEL_TOKENS):
        return False
    if looks_like_non_product_receipt_label and looks_like_non_product_receipt_label(label):
        return False
    return True


def _decimal(value: str | None) -> Decimal | None:
    try:
        return Decimal(str(value or "").replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return None


def _label_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def has_existing_line_for_label(lines: list[dict[str, Any]], label: str) -> bool:
    label_key = _label_key(label)
    if not label_key:
        return False
    for line in lines or []:
        existing = line.get("raw_label") or line.get("normalized_label")
        if _label_key(existing) == label_key:
            return True
    return False


def should_append_jumbo_app_quantity_detail_pair(
    *,
    lines: list[str],
    extracted: list[dict[str, Any]],
    source_index: int,
    store_name: str | None = None,
    filename: str | None = None,
    looks_like_non_product_receipt_label: Callable[[str], bool] | None = None,
) -> dict[str, Any] | None:
    if not is_jumbo_context(store_name=store_name, filename=filename):
        return None
    if source_index <= 0 or source_index >= len(lines):
        return None

    detail_line = re.sub(r"\s+", " ", str(lines[source_index] or "")).strip()
    detail_match = JUMBO_APP_QUANTITY_DETAIL_RE.match(detail_line)
    if not detail_match:
        return None

    label = normalize_jumbo_app_label(lines[source_index - 1])
    if not looks_like_safe_jumbo_app_pair_label(
        label,
        looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
    ):
        return None
    if has_existing_line_for_label(extracted, label):
        return None

    quantity = _decimal(detail_match.group("qty"))
    amount1 = _decimal(detail_match.group("amount1"))
    amount2 = _decimal(detail_match.group("amount2")) if detail_match.group("amount2") else amount1
    if quantity is None or amount1 is None or amount2 is None:
        return None
    if quantity <= 0 or amount1 <= 0 or amount2 <= 0:
        return None
    calculated_total = (quantity * amount1).quantize(Decimal("0.01"))
    if detail_match.group("amount2") and abs(calculated_total - amount2) > Decimal("0.01"):
        return None

    return {
        "label": label,
        "qty_raw": detail_match.group("qty"),
        "amount1_raw": detail_match.group("amount1"),
        "amount2_raw": detail_match.group("amount2") or detail_match.group("amount1"),
        "source_index": source_index,
        "raw_line": detail_line,
        "normalized_line": detail_line,
    }
