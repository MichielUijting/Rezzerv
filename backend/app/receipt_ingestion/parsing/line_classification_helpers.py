from __future__ import annotations

import re
from typing import Any, Callable

from app.receipt_ingestion.line_classifier import classify_receipt_text_line

ShouldSkipLine = Callable[[str], bool]
LooksLikeNonProductLabel = Callable[[str | None], bool]
LooksLikeItemLabelOnly = Callable[[str], bool]
IsValidatedSavingsActionLine = Callable[[dict[str, Any]], bool]


RECEIPT_NON_PRODUCT_LABEL_TOKENS = (
    'btw', 'vat', 'totaal', 'subtotaal', 'netto', 'bruto', 'bedrag', 'betaling',
    'betaald', 'bankpas', 'pin', 'pinnen', 'vpay', 'v-pay', 'maestro', 'terminal',
    'transactie', 'autorisatie', 'auth', 'kaart', 'kaartserienummer', 'datum', 'tijd',
    'groep', 'incl', 'excl', 'periode', 'leesmethod', 'contactloos', 'klantticket',
    'kopie', 'bonnummer', 'kassanr', 'kassa', 'filiaal', 'openingstijden', 'www.',
    'http', 'welkom', 'bedankt', 'dank u', 'tot ziens', 'coupon', 'actiecode',
    'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart',
)


def _contains_letter(value: str | None) -> bool:
    return any(ch.isalpha() for ch in str(value or ''))


def _looks_like_non_product_receipt_label(label: str | None) -> bool:
    """Return True for OCR lines that should never become inventory articles."""
    candidate = re.sub(r'\s+', ' ', str(label or '')).strip(' .:-')
    if not candidate:
        return True
    lowered = candidate.lower()
    if re.fullmatch(r'[-+]?\d+(?:[\.,]\d+)?(?:\s+[-+]?\d+(?:[\.,]\d+)?)*', candidate):
        return True
    if re.fullmatch(r'[\d\s,\.:%/\-+xX]+', candidate):
        return True
    if re.search(r'-?\d{1,6}(?:[\.,]\d{2})', lowered) and any(token in lowered for token in ('koopzegel', 'koopzegels', 'pluspunten', 'korting')):
        return False
    for token in RECEIPT_NON_PRODUCT_LABEL_TOKENS:
        if token in {'www.', 'http'}:
            if token in lowered:
                return True
            continue
        if re.search(rf'(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])', lowered):
            return True
    if re.search(r'\b\d{1,2}:\d{2}\b', lowered):
        return True
    if re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', lowered):
        return True
    letters = [ch for ch in candidate if ch.isalpha()]
    digits = re.findall(r'\d', candidate)
    if len(letters) < 2 and len(digits) >= 2:
        return True
    if len(candidate) > 80 and sum(ch.isdigit() for ch in candidate) > 10:
        return True
    return False


def _is_invalid_aldi_article_candidate(label: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(label or '')).strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    if 'btw' in lowered or 'bruto' in lowered or 'netto' in lowered:
        return True
    if re.fullmatch(r'[\d\s,\.%xX-]+', candidate):
        return True
    if re.match(r'^\d{1,2}(?:[\.,]\d{2})?[%xX]?\s+\d{1,6}(?:[\.,]\d{2})$', candidate):
        return True
    return False


def _looks_like_item_label_only(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    should_skip_receipt_line: ShouldSkipLine,
) -> bool:
    candidate = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not candidate or should_skip_receipt_line(candidate):
        return False
    if not _contains_letter(candidate):
        return False
    if re.search(r'\d+[\.,]\d{2}', candidate):
        return False
    return True


def _filter_non_product_receipt_lines(
    lines: list[dict[str, Any]],
    *,
    looks_like_non_product_receipt_label: LooksLikeNonProductLabel = _looks_like_non_product_receipt_label,
    is_validated_savings_action_line: IsValidatedSavingsActionLine,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in lines or []:
        label = str(line.get('raw_label') or line.get('normalized_label') or '').strip()
        is_validated_savings_line = is_validated_savings_action_line(line)
        if looks_like_non_product_receipt_label(label) and not is_validated_savings_line:
            continue
        key = (
            re.sub(r'\s+', ' ', label).strip().lower(),
            str(line.get('line_total') or ''),
            str(line.get('source_index') or ''),
        )
        if key in seen:
            continue
        seen.add(key)
        # Preserve diagnostic/runtime-only fields such as producer_trace.
        filtered.append(dict(line))
    return filtered


def _classify_receipt_text_line(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    detail_only_re: re.Pattern | None = None,
    qty_first_re: re.Pattern | None = None,
    label_first_re: re.Pattern | None = None,
    should_skip_receipt_line: ShouldSkipLine,
    looks_like_non_product_receipt_label: LooksLikeNonProductLabel = _looks_like_non_product_receipt_label,
    looks_like_item_label_only: LooksLikeItemLabelOnly,
) -> str:
    return classify_receipt_text_line(
        line,
        store_name=store_name,
        filename=filename,
        detail_only_re=detail_only_re,
        qty_first_re=qty_first_re,
        label_first_re=label_first_re,
        should_skip_receipt_line=should_skip_receipt_line,
        looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
        looks_like_item_label_only=looks_like_item_label_only,
    )
