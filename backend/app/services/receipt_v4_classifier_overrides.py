from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

PRICE_RE = re.compile(r"-?\d{1,6}[\.,]\d{2}")


def has_price(value: str) -> bool:
    return bool(PRICE_RE.search(str(value or "")))


def parse_price(value: str) -> Decimal | None:
    matches = PRICE_RE.findall(str(value or ""))
    if not matches:
        return None
    raw = matches[-1].replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def is_payment_or_total_line(value: str) -> bool:
    text = str(value or "").strip().lower()
    markers = (
        "totaal",
        "subtotaal",
        "te betalen",
        "betaling",
        "betaald",
        "btw",
        "wisselgeld",
        "bankpas",
        "contant",
    )
    return any(marker in text for marker in markers)


def is_discount_line(value: str) -> bool:
    text = str(value or "").strip().lower()
    markers = ("korting", "bonus", "voordeel")
    return any(marker in text for marker in markers)


def keep_priced_article_candidate(value: str) -> bool:
    """Keep priced supermarket lines as article candidates unless clearly non-product.

    This module is intentionally small and focused for the V4 supermarket baseline.
    The existing parser remains leading; this helper only prevents priced product
    rows from being discarded too early.
    """
    text = str(value or "").strip().lower()
    if not text or not has_price(text):
        return False
    return not is_payment_or_total_line(text)


def normalize_discount_line(value: str) -> dict[str, object] | None:
    """Represent discount rows consistently for final receipt validation."""
    if not is_discount_line(value):
        return None
    amount = parse_price(value)
    if amount is None:
        return None
    return {
        "line_total": None,
        "discount_amount": float(abs(amount)),
    }
