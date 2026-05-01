from __future__ import annotations

import re

PRICE_RE = re.compile(r"-?\d{1,6}[\.,]\d{2}")


def has_price(value: str) -> bool:
    return bool(PRICE_RE.search(str(value or "")))


def keep_priced_article_candidate(value: str) -> bool:
    """Keep priced supermarket lines as article candidates unless clearly non-product.

    This module is intentionally small and focused for the V4 supermarket baseline.
    The existing parser remains leading; this helper only prevents priced product
    rows from being discarded too early.
    """
    text = str(value or "").strip().lower()
    if not text or not has_price(text):
        return False

    non_product_markers = (
        "totaal",
        "subtotaal",
        "te betalen",
        "betaling",
        "betaald",
        "btw",
        "wisselgeld",
    )
    return not any(marker in text for marker in non_product_markers)
