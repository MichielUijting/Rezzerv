from __future__ import annotations

import re
from collections.abc import Callable

BLOCKING_CLASSIFICATIONS = {'ignore', 'metadata', 'footer_payment_tax'}
FOOTER_TOKENS = ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')
DUTCH_DAY_TOKENS = ('maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')
LegacyLineCheck = Callable[[str], bool]


def _default_false(_: str) -> bool:
    return False


def _footer_or_metadata(lowered: str) -> str:
    if any(token in lowered for token in FOOTER_TOKENS):
        return 'footer_payment_tax'
    return 'metadata'


def classify_receipt_text_line(
    line: str,
    *,
    store_name: str | None = None,
    filename: str | None = None,
    detail_only_re: re.Pattern | None = None,
    qty_first_re: re.Pattern | None = None,
    label_first_re: re.Pattern | None = None,
    should_skip_receipt_line: LegacyLineCheck | None = None,
    looks_like_non_product_receipt_label: LegacyLineCheck | None = None,
    looks_like_item_label_only: LegacyLineCheck | None = None,
) -> str:
    del store_name, filename
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if len(normalized) < 2:
        return 'ignore'

    lowered = normalized.lower()
    upper_compact = normalized.upper().replace(',', '.')

    if re.fullmatch(r'(?:ZA|ZO|ZON)\s+\d{1,2}\.\d{2}', upper_compact):
        return 'metadata'
    if re.match(r'^[A-Z]\s+\d{1,2}[,.]\d{2}%\b', normalized.upper()):
        return 'footer_payment_tax'
    if any(day in lowered for day in DUTCH_DAY_TOKENS) and ('t/m' in lowered or ' tot ' in lowered):
        return 'metadata'
    if re.fullmatch(r'\d{1,4}[.]\d{2}', normalized) or re.fullmatch(r'\d{1,4},\d{2}', normalized):
        return 'footer_payment_tax'
    if re.search(r'\bzegels?\b|\bzege1s\b|\bpluspunten\b', lowered) and re.search(r'\d{1,2}:\d{2}|\d{3,}', normalized):
        return 'footer_payment_tax'

    should_skip = should_skip_receipt_line or _default_false
    if should_skip(normalized):
        return _footer_or_metadata(lowered)

    looks_non_product = looks_like_non_product_receipt_label or _default_false
    if looks_non_product(normalized):
        return _footer_or_metadata(lowered)

    if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
        return 'metadata'
    if detail_only_re is not None and detail_only_re.match(normalized):
        return 'amount_detail'
    if qty_first_re is not None and qty_first_re.match(normalized):
        return 'product_candidate'
    if label_first_re is not None and label_first_re.match(normalized):
        return 'product_candidate'

    looks_item_label = looks_like_item_label_only or _default_false
    if looks_item_label(normalized):
        return 'continuation'
    return 'ignore'


def classification_allows_append(classification: str | None) -> bool:
    return classification not in BLOCKING_CLASSIFICATIONS
