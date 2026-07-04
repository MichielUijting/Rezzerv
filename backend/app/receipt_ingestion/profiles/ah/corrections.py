"""
Technical Design Reference:
- TD Section: TD-03 Receipt ingestion en parsers
- Module Role: Receipt source parsing and data extraction
- Runtime Type: production
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

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

def _ah_label_key(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).strip()


def _ah_existing_label_keys(lines: list[dict[str, Any]] | None) -> set[str]:
    keys: set[str] = set()
    for line in lines or []:
        if not isinstance(line, dict):
            continue
        label = (
            line.get("raw_label")
            or line.get("normalized_label")
            or line.get("display_label")
            or ""
        )
        key = _ah_label_key(str(label))
        if key:
            keys.add(key)
    return keys


def _ah_sum_lines_net(lines: list[dict[str, Any]] | None, discount_total: Decimal | None = None) -> Decimal:
    line_sum = sum(
        (_r9_38e1_decimal(line.get("line_total")) for line in (lines or []) if isinstance(line, dict)),
        Decimal("0.00"),
    )
    line_discount_sum = sum(
        (_r9_38e1_decimal(line.get("discount_amount")) for line in (lines or []) if isinstance(line, dict)),
        Decimal("0.00"),
    )
    receipt_discount = _r9_38e1_decimal(discount_total)
    return (line_sum + line_discount_sum + receipt_discount).quantize(Decimal("0.01"))


def _ah_extract_weight_product_candidates_from_reliable_lines(reliable_lines: list[str] | None) -> list[dict[str, Any]]:
    """Extract AH weighted article rows from a reliable OCR stream.

    Example:
    0,587K CONFERENCE 1,11
    """
    candidates: list[dict[str, Any]] = []

    blocked_tokens = (
        "subtotaal",
        "totaal",
        "bonus",
        "voordeel",
        "koopzegel",
        "koopzegels",
        "prijs per kg",
        "pinnen",
        "betaald",
        "btw",
    )

    for index, raw in enumerate(reliable_lines or []):
        line = re.sub(r"\s+", " ", str(raw or "")).strip()
        low = line.lower()
        if not line:
            continue
        if any(token in low for token in blocked_tokens):
            continue

        # AH OCR variants commonly read weight as 0,587K / 0,587k / 0,587 KG.
        match = re.search(
            r"(?<!\d)(\d+[,.]\d{3})\s*(?:k|kg)?\s+([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9 '\-]{2,}?)\s+(\d{1,5}[,.]\d{2})(?!\d)",
            line,
            re.I,
        )
        if not match:
            continue

        try:
            quantity = Decimal(match.group(1).replace(",", ".")).quantize(Decimal("0.001"))
        except Exception:
            quantity = None
        label = re.sub(r"\s+", " ", match.group(2)).strip(" .:-")
        total = _parse_decimal(match.group(3))

        if quantity is None or quantity <= Decimal("0.000"):
            continue
        if total is None or total <= Decimal("0.00"):
            continue
        if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", label):
            continue

        unit = (total / quantity).quantize(Decimal("0.01"))

        candidates.append({
            "raw_label": label,
            "normalized_label": label.upper(),
            "quantity": float(quantity),
            "unit_price": float(unit),
            "line_total": float(total),
            "discount_amount": None,
            "include_in_receipt_total": True,
            "exclude_from_inventory": False,
            "source_index": index,
            "producer_trace": {
                "parser_path": "ah_image_balance_repair.weight_product_from_reliable_ocr",
                "function_name": "_ah_repair_image_balance_from_reliable_lines",
                "raw_line": line,
                "source_index": index,
                "classification": "product_candidate",
                "append_allowed": True,
            },
        })

    return candidates


def _ah_extract_bonus_discount_from_reliable_lines(reliable_lines: list[str] | None) -> Decimal | None:
    total = Decimal("0.00")

    for raw in reliable_lines or []:
        line = re.sub(r"\s+", " ", str(raw or "")).strip()
        low = line.lower()
        if "bonuskaart" in low or "bonus box premium" in low:
            continue
        if "bonus" not in low:
            continue

        for token in re.findall(r"(?<!\d)(-\s*\d{1,5}[,.]\d{2}|[=−]\s*\d{1,5}[,.]\d{2})(?!\d)", line):
            normalized = token.replace(" ", "").replace("−", "-").replace("=", "-")
            amount = _parse_decimal(normalized)
            if amount is not None and amount < Decimal("0.00"):
                total += amount

    return total.quantize(Decimal("0.01")) if total != Decimal("0.00") else None


def _ah_apply_discount_to_best_bonus_target(lines: list[dict[str, Any]], discount: Decimal) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not lines or discount == Decimal("0.00"):
        return lines, None

    refined = [dict(line) if isinstance(line, dict) else line for line in lines]

    candidate_indices: list[int] = []
    for index, line in enumerate(refined):
        if not isinstance(line, dict):
            continue
        trace = line.get("producer_trace") or {}
        raw = str(trace.get("raw_line") or line.get("raw_label") or "")
        label = str(line.get("raw_label") or line.get("normalized_label") or "")

        if "koopzegel" in label.lower():
            continue
        if re.search(r"\sB\s*$", raw, re.I):
            candidate_indices.append(index)

    if not candidate_indices:
        for index, line in enumerate(refined):
            if not isinstance(line, dict):
                continue
            label = str(line.get("raw_label") or line.get("normalized_label") or "")
            if "koopzegel" in label.lower():
                continue
            if _r9_38e1_decimal(line.get("line_total")) > Decimal("0.00"):
                candidate_indices.append(index)

    if not candidate_indices:
        return lines, None

    target_index = max(
        candidate_indices,
        key=lambda idx: _r9_38e1_decimal(refined[idx].get("line_total")) if isinstance(refined[idx], dict) else Decimal("0.00"),
    )

    current = _r9_38e1_decimal(refined[target_index].get("discount_amount"))
    refined[target_index]["discount_amount"] = float((current + discount).quantize(Decimal("0.01")))

    return refined, {
        "target_index": int(target_index),
        "target_label": refined[target_index].get("raw_label"),
        "discount_amount": float(discount),
    }


def _ah_repair_image_balance_from_reliable_lines(
    *,
    reliable_lines: list[str],
    lines: list[dict[str, Any]],
    store_name: str | None,
    total_amount: Decimal | None,
    discount_total: Decimal | None,
) -> tuple[list[dict[str, Any]], Decimal | None, dict[str, Any] | None]:
    """AH image OCR balance repair using reliable OCR financial/product evidence.

    This is deliberately total-guarded:
    no line, discount, or status is changed unless the resulting net sum exactly
    matches the visible receipt total.
    """
    if not lines or total_amount is None:
        return lines, discount_total, None
    if not _is_ah_store_context(store_name, reliable_lines):
        return lines, discount_total, None

    total = _r9_38e1_decimal(total_amount)
    before_net = _ah_sum_lines_net(lines, discount_total)
    if before_net == total:
        return lines, discount_total, None

    existing_keys = _ah_existing_label_keys(lines)
    weight_candidates = []
    for candidate in _ah_extract_weight_product_candidates_from_reliable_lines(reliable_lines):
        key = _ah_label_key(candidate.get("raw_label"))
        if not key:
            continue
        if key in existing_keys:
            continue
        if any(key in existing or existing in key for existing in existing_keys if len(existing) >= 4 and len(key) >= 4):
            continue
        weight_candidates.append(candidate)

    bonus_discount = _ah_extract_bonus_discount_from_reliable_lines(reliable_lines)

    attempts: list[tuple[list[dict[str, Any]], Decimal | None, str]] = [
        ([], None, "none"),
    ]

    for candidate in weight_candidates:
        attempts.append(([candidate], None, "weight_only"))

    if bonus_discount is not None:
        attempts.append(([], bonus_discount, "bonus_only"))
        for candidate in weight_candidates:
            attempts.append(([candidate], bonus_discount, "weight_plus_bonus"))

    for add_lines, discount, mode in attempts:
        if mode == "none":
            continue

        candidate_lines = [dict(line) if isinstance(line, dict) else line for line in lines]
        candidate_lines.extend(dict(line) for line in add_lines)

        discount_application = None
        candidate_discount_total = discount_total

        if discount is not None:
            candidate_lines, discount_application = _ah_apply_discount_to_best_bonus_target(candidate_lines, discount)

        candidate_net = _ah_sum_lines_net(candidate_lines, candidate_discount_total)

        if candidate_net == total:
            return candidate_lines, candidate_discount_total, {
                "r9_m2c2i128_ah_image_balance_repair": {
                    "applied": True,
                    "mode": mode,
                    "before_net": float(before_net),
                    "after_net": float(candidate_net),
                    "total_amount": float(total),
                    "added_lines": [
                        {
                            "raw_label": line.get("raw_label"),
                            "quantity": line.get("quantity"),
                            "line_total": line.get("line_total"),
                            "source_index": line.get("source_index"),
                        }
                        for line in add_lines
                    ],
                    "bonus_discount": float(discount) if discount is not None else None,
                    "discount_application": discount_application,
                    "reason": "AH reliable OCR evidence closes receipt total exactly",
                }
            }

    return lines, discount_total, None

