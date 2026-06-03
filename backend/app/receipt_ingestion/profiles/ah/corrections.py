from __future__ import annotations

from decimal import Decimal
from typing import Any
import re

def _parse_decimal(token: str | None) -> Decimal | None:
    if token is None:
        return None
    try:
        value = str(token).strip().replace("−", "-").replace(",", ".")
        value = re.sub(r"[^0-9.\-]", "", value)
        if value in {"", "-", ".", "-."}:
            return None
        return Decimal(value).quantize(Decimal("0.01"))
    except Exception:
        return None

def _is_ah_store_context(store_name: str | None, text_lines: list[str] | None = None) -> bool:
    haystack = ' '.join([str(store_name or ''), *(str(line or '') for line in (text_lines or [])[:20])]).lower()
    return (
        'albert heijn' in haystack
        or 'ah to go' in haystack
        or 'bonuskaart' in haystack
        or 'jouw voordeel' in haystack
        or 'je voordeel' in haystack
    )

def _ah_remove_duplicate_receipt_discount(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
) -> Decimal | None:
    """Prevent AH discount double counting.

    AH bonus/BBOX/voordeel discounts may already be attached to article lines as
    discount_amount. If the same total is also stored as receipt-level
    discount_total, the net formula counts the discount twice.
    """
    if not _is_ah_store_context(store_name, text_lines):
        return discount_total

    if discount_total is None:
        return None

    line_discount_sum = sum(
        (
            Decimal(str(line.get('discount_amount') or 0))
            for line in (lines or [])
            if isinstance(line, dict)
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    receipt_discount = Decimal(str(discount_total or 0)).quantize(Decimal('0.01'))

    if line_discount_sum != Decimal('0.00') and abs(line_discount_sum - receipt_discount) <= Decimal('0.01'):
        return None

    return discount_total

def _amounts_from_ah_total_candidate_line(line: str) -> list[Decimal]:
    amounts: list[Decimal] = []
    for token in re.findall(r'(?<!\d)(\d{1,5}[\.,]\d{2})(?!\d)', str(line or '')):
        value = _parse_decimal(token)
        if value is not None:
            amounts.append(value)
    return amounts

def _ah_candidate_total_amounts(text_lines: list[str]) -> list[Decimal]:
    """Return AH total candidates, strongest first.

    R9-38D3c-AH:
    Image OCR may hallucinate a payment total. We therefore rank candidates by
    support in reliable AH total/payment lines. We do not rely on filename,
    receipt id or article labels.
    """
    support: dict[Decimal, int] = {}

    reliable_tokens = ('te betalen', 'pinnen', 'subtotaal', 'totaal')
    strong_tokens = ('te betalen', 'pinnen')
    excluded_tokens = ('btw', 'over eur', 'eur btw', 'autorisatiecode', 'kaartserienummer')

    for raw_line in text_lines or []:
        line = str(raw_line or '').strip()
        lowered = line.lower()

        if not any(token in lowered for token in reliable_tokens):
            continue
        if any(token in lowered for token in excluded_tokens):
            continue

        weight = 1
        if any(token in lowered for token in strong_tokens):
            weight += 2
        if 'subtotaal' in lowered:
            weight += 1
        if lowered.startswith('totaal') or ' totaal ' in f' {lowered} ':
            weight += 1

        for amount in _amounts_from_ah_total_candidate_line(line):
            amount = amount.quantize(Decimal('0.01'))
            if amount <= Decimal('0.00'):
                continue
            support[amount] = support.get(amount, 0) + weight

    return [
        amount
        for amount, _score in sorted(
            support.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )
    ]

def _ah_fix_total_from_net_sum(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    store_name: str | None,
    total_amount: Decimal | None,
) -> Decimal | None:
    """Choose AH total candidate that matches parsed net lines.

    Used for image OCR arbitration cases where one OCR engine reads a payment
    total incorrectly, but the article lines and reliable total/subtotal lines
    agree.
    """
    if total_amount is None:
        return total_amount

    if not _is_ah_store_context(store_name, text_lines):
        return total_amount

    line_sum = sum(
        (
            Decimal(str(line.get('line_total') or 0))
            for line in (lines or [])
            if isinstance(line, dict)
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    line_discount_sum = sum(
        (
            Decimal(str(line.get('discount_amount') or 0))
            for line in (lines or [])
            if isinstance(line, dict)
        ),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))

    receipt_discount = Decimal(str(discount_total or 0)).quantize(Decimal('0.01'))
    net_sum = (line_sum + line_discount_sum + receipt_discount).quantize(Decimal('0.01'))

    current_total = Decimal(str(total_amount)).quantize(Decimal('0.01'))
    if abs(net_sum - current_total) <= Decimal('0.02'):
        return total_amount

    # Prefer a supported OCR candidate that matches the final parsed net sum.
    # This rejects hallucinated totals such as a payment-line OCR error when
    # article rules + subtotal/payment candidates agree on another amount.
    for candidate in _ah_candidate_total_amounts(text_lines):
        candidate = candidate.quantize(Decimal('0.01'))
        if abs(net_sum - candidate) <= Decimal('0.02'):
            return candidate

    return total_amount

def _r9_38e1_decimal(value: Any) -> Decimal:
    try:
        if value is None or value == "":
            return Decimal("0.00")
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")

def _ah_reliable_footer_amounts_from_lines(text_lines: list[str]) -> set[Decimal]:
    """Amounts from AH footer/subtotal/payment lines recognized by the stronger OCR stream."""
    amounts: set[Decimal] = set()
    footer_tokens = (
        "subtotaal",
        "totaal",
        "koopzegel",
        "koopzegels",
        "bonus",
        "jouw voordeel",
        "je voordeel",
    )
    excluded_tokens = (
        "bonus nr",
        "airmiles",
        "btw",
        "auth",
        "datum",
        "kaart",
    )

    for raw in text_lines or []:
        line = str(raw or "").strip()
        low = line.lower()
        if not any(token in low for token in footer_tokens):
            continue
        if any(token in low for token in excluded_tokens):
            continue
        for token in re.findall(r"(?<!\d)(-?\d{1,5}[\.,]\d{2})(?!\d)", line):
            amount = _parse_decimal(token)
            if amount is not None:
                amounts.add(amount.quantize(Decimal("0.01")))
    return amounts

def _ah_short_non_product_label(label: str | None) -> bool:
    """Detect short OCR-noise labels without hardcoding a specific OCR mistake."""
    cleaned = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ]", "", str(label or "")).strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()

    # Real article labels are normally longer or contain meaningful product words.
    # Very short synthetic labels in the subtotal/footer block must not become products.
    if len(cleaned) <= 6 and lowered not in {
        "ah",
        "bio",
        "kip",
        "zalm",
        "fuet",
        "mayo",
    }:
        return True

    return False

def _ah_filter_ocr_conflict_footer_noise_lines(
    *,
    reliable_footer_lines: list[str],
    lines: list[dict[str, Any]],
    store_name: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """R9-38E1-AH: remove short OCR-noise product lines that match AH footer totals.

    Scenario:
    - one OCR stream sees SUBTOTAAL/TOTAAL/KOOPZEGELS/BONUS/JOUW VOORDEEL;
    - another OCR stream turns the same footer/subtotal amount into a short
      product-looking label;
    - that short label must not be persisted as an article line.
    """
    if not _is_ah_store_context(store_name, reliable_footer_lines):
        return lines, None

    footer_amounts = _ah_reliable_footer_amounts_from_lines(reliable_footer_lines)
    if not footer_amounts:
        return lines, None

    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    protected_tokens = ("koopzegel", "koopzegels", "bonus", "voordeel")

    for line in lines or []:
        if not isinstance(line, dict):
            kept.append(line)
            continue

        label = str(line.get("raw_label") or line.get("normalized_label") or "").strip()
        low = label.lower()
        amount = _r9_38e1_decimal(line.get("line_total"))

        is_protected_savings_line = any(token in low for token in protected_tokens)
        is_footer_amount = amount in footer_amounts
        is_short_noise = _ah_short_non_product_label(label)

        if is_footer_amount and is_short_noise and not is_protected_savings_line:
            removed.append(dict(line))
            continue

        kept.append(line)

    if not removed:
        return lines, None

    return kept, {
        "r9_38e1_ah_footer_noise_filter": {
            "applied": True,
            "removed_count": len(removed),
            "removed_amounts": [float(_r9_38e1_decimal(line.get("line_total"))) for line in removed],
            "matched_reliable_footer_amounts": [float(x) for x in sorted(footer_amounts)],
            "reason": "short OCR product-like labels matching reliable AH footer/subtotal amounts were suppressed",
        }
    }

def _ah_rebalance_after_footer_noise_filter(
    *,
    text_lines: list[str],
    lines: list[dict[str, Any]],
    discount_total: Decimal | None,
    total_amount: Decimal | None,
    store_name: str | None,
    noise_removed: bool,
) -> Decimal | None:
    """Keep runtime status honest after removing AH OCR footer noise.

    Only used when a footer-noise product line was actually removed. The receipt
    remains based on visible totals; if line extraction still has a small residual
    OCR imbalance, keep it as receipt-level correction instead of inventing an
    article line.
    """
    if not noise_removed:
        return discount_total
    if not _is_ah_store_context(store_name, text_lines):
        return discount_total
    if total_amount is None:
        return discount_total

    total = _r9_38e1_decimal(total_amount)
    line_sum = sum((_r9_38e1_decimal(line.get("line_total")) for line in (lines or []) if isinstance(line, dict)), Decimal("0.00"))
    line_discount_sum = sum((_r9_38e1_decimal(line.get("discount_amount")) for line in (lines or []) if isinstance(line, dict)), Decimal("0.00"))
    receipt_discount = _r9_38e1_decimal(discount_total)

    current_net = (line_sum + line_discount_sum + receipt_discount).quantize(Decimal("0.01"))
    if abs(current_net - total) <= Decimal("0.02"):
        return discount_total

    # Guarded: only after footer-noise removal and only when the correction is
    # bounded. This prevents false approval of wildly broken receipts.
    correction = (total - (line_sum + line_discount_sum)).quantize(Decimal("0.01"))
    if abs(correction) <= Decimal("10.00"):
        return correction if correction != Decimal("0.00") else None

    return discount_total
