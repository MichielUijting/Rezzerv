from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Callable

TRAILING_AMOUNT_RE = re.compile(r"(?<!\d)(?P<amount>-?\d{1,6}(?:[\.,]\d{2}))(?!\d)\s*(?:EUR|[A-Z]{1,3})?\s*$", re.IGNORECASE)
DISCOUNT_COMPENSATION_RE = re.compile(
    r"^\s*(?P<label>(?:gratis|actie|korting|bonus|voordeel|prijsvoordeel)[A-Za-z0-9À-ÖØ-öø-ÿ .:'/-]*)\s+"
    r"(?P<amount>-\d{1,6}(?:[\.,]\d{2}))\s*(?:EUR|[A-Z]{1,3})?\s*$",
    re.IGNORECASE,
)

_NON_PRODUCT_LABEL_TOKENS = (
    "totaal",
    "subtotaal",
    "btw",
    "betaald",
    "betaling",
    "bankpas",
    "pin",
    "vpay",
    "v-pay",
    "terminal",
    "transactie",
    "kaart",
    "saldo",
    "punten",
    "koopzegel",
    "koopzegels",
    "zegel",
    "zegels",
    "openingstijden",
    "medewerker",
    "store",
    "pos",
    "www",
    "http",
)


def _decimal(value: str | None) -> Decimal | None:
    try:
        return Decimal(str(value or "").replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return None


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _label_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _gateway_safe_label(value: str | None) -> str:
    """Normalize noisy all-caps OCR product labels for the append gateway.

    Some OCR lines classify as ignore when the label is entirely uppercase, even
    though the product/discount cluster itself is valid. The canonical stored
    product label should remain readable and gateway-acceptable without changing
    the financial semantics.
    """
    label = _clean_text(value).strip(" .:-")
    if label and label.upper() == label and re.search(r"[A-ZÀ-ÖØ-Þ]", label):
        words = [word.capitalize() if word.isupper() else word for word in label.split()]
        return " ".join(words)
    return label


def _looks_like_safe_article_label(value: str | None, *, is_invalid_label: Callable[[str], bool] | None = None) -> bool:
    label = _clean_text(value).strip(" .:-")
    if len(label) < 3:
        return False
    lowered = label.lower()
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
        return False
    if any(token in lowered for token in _NON_PRODUCT_LABEL_TOKENS):
        return False
    if is_invalid_label is not None and is_invalid_label(label):
        return False
    return True


def _has_existing_line_for_label(lines: list[dict[str, Any]], label: str) -> bool:
    label_key = _label_key(label)
    if not label_key:
        return False
    for line in lines or []:
        existing = line.get("raw_label") or line.get("normalized_label")
        if _label_key(existing) == label_key:
            return True
    return False


def _labels_are_related(product_label: str, discount_label: str) -> bool:
    product_tokens = [token for token in re.split(r"\W+", product_label.lower()) if len(token) >= 4]
    discount_tokens = [token for token in re.split(r"\W+", discount_label.lower()) if len(token) >= 4]
    if not product_tokens or not discount_tokens:
        return False
    if any(token in discount_tokens for token in product_tokens):
        return True
    product_compact = _label_key(product_label)
    discount_compact = _label_key(discount_label)
    return bool(product_compact and discount_compact and (product_compact in discount_compact or discount_compact in product_compact))


def should_append_generic_article_discount_cluster(
    *,
    lines: list[str],
    extracted: list[dict[str, Any]],
    source_index: int,
    is_invalid_label: Callable[[str], bool] | None = None,
) -> dict[str, Any] | None:
    """Detect a generic article discount/free-product cluster.

    Pattern:
    - product line with positive amount, e.g. "JUMBO STROOPWAFELS 1,65"
    - next line with negative discount/free compensation, e.g. "Gratis stroopwafels -1,65"

    Returns one candidate article line carrying gross line_total and discount_amount.
    It intentionally excludes savings/value lines such as koopzegels.
    """
    if source_index < 0 or source_index + 1 >= len(lines):
        return None

    product_line = _clean_text(lines[source_index])
    product_match = TRAILING_AMOUNT_RE.search(product_line)
    if not product_match:
        return None
    product_amount = _decimal(product_match.group("amount"))
    if product_amount is None or product_amount <= 0:
        return None
    product_label_raw = product_line[: product_match.start()].strip(" .:-")
    product_label = _gateway_safe_label(product_label_raw)
    if not _looks_like_safe_article_label(product_label, is_invalid_label=is_invalid_label):
        return None

    discount_line = _clean_text(lines[source_index + 1])
    discount_match = DISCOUNT_COMPENSATION_RE.match(discount_line)
    if not discount_match:
        return None
    discount_amount = _decimal(discount_match.group("amount"))
    if discount_amount is None or discount_amount >= 0:
        return None
    discount_label = _clean_text(discount_match.group("label"))
    if not _labels_are_related(product_label_raw, discount_label):
        return None

    if _has_existing_line_for_label(extracted, product_label):
        return None

    return {
        "label": product_label,
        "qty_raw": "1",
        "amount1_raw": str(product_amount),
        "amount2_raw": str(product_amount),
        "discount_amount": str(discount_amount),
        "source_index": source_index,
        "discount_source_index": source_index + 1,
        "raw_line": product_line,
        "normalized_line": product_label,
        "discount_raw_line": discount_line,
    }
