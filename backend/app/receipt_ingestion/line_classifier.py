from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

BLOCKING_CLASSIFICATIONS = {'ignore', 'metadata', 'footer_payment_tax'}
FOOTER_TOKENS = ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')
DUTCH_DAY_TOKENS = ('maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')
ARTICLE_CLASSIFICATIONS = {'product_candidate'}
NON_ARTICLE_CLASSIFICATIONS = {'ignore', 'metadata', 'footer_payment_tax'}
SUPPORTING_ARTICLE_CLASSIFICATIONS = {'amount_detail', 'continuation'}
LegacyLineCheck = Callable[[str], bool]


def _default_false(_: str) -> bool:
    return False


def _footer_or_metadata(lowered: str) -> str:
    if any(token in lowered for token in FOOTER_TOKENS):
        return 'footer_payment_tax'
    return 'metadata'


def _non_article_reason(classification: str | None, line: str) -> str:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    lowered = normalized.lower()
    if classification == 'footer_payment_tax':
        if any(token in lowered for token in ('totaal', 'subtotaal')):
            return 'total_or_subtotal_line'
        if any(token in lowered for token in ('btw', 'vat')):
            return 'vat_line'
        if any(token in lowered for token in ('betaal', 'bankpas', 'pin', 'terminal', 'transactie')):
            return 'payment_line'
        if re.fullmatch(r'\d{1,4}[.,]\d{2}', normalized):
            return 'standalone_amount_line'
        return 'footer_payment_tax_line'
    if classification == 'metadata':
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
            return 'date_or_time_metadata'
        if any(day in lowered for day in DUTCH_DAY_TOKENS):
            return 'date_or_period_metadata'
        return 'receipt_metadata'
    if classification == 'ignore':
        return 'noise_or_unclassified_line'
    if classification == 'amount_detail':
        return 'supporting_amount_detail_not_standalone_article'
    if classification == 'continuation':
        return 'label_continuation_needs_article_context'
    return 'unknown_classification'


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


def diagnose_article_line_classification(
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
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return explicit article-vs-non-article diagnostics without changing parsing.

    R9-11A contract:
    - ARTIKEL_MET_PRIJS is a standalone product candidate with price.
    - GEEN_ARTIKEL is metadata/footer/payment/VAT/noise.
    - Supporting lines are diagnostic only and need parser context before they can
      become part of an article. This function does not append or drop lines.
    """
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    classification = classify_receipt_text_line(
        normalized,
        store_name=store_name,
        filename=filename,
        detail_only_re=detail_only_re,
        qty_first_re=qty_first_re,
        label_first_re=label_first_re,
        should_skip_receipt_line=should_skip_receipt_line,
        looks_like_non_product_receipt_label=looks_like_non_product_receipt_label,
        looks_like_item_label_only=looks_like_item_label_only,
    )
    if classification in ARTICLE_CLASSIFICATIONS:
        article_decision = 'ARTIKEL_MET_PRIJS'
        reason = 'matched_article_with_price_pattern'
        include_in_article_sum = True
    elif classification in SUPPORTING_ARTICLE_CLASSIFICATIONS:
        article_decision = 'ONDERSTEUNENDE_ARTIKELINFO'
        reason = _non_article_reason(classification, normalized)
        include_in_article_sum = False
    else:
        article_decision = 'GEEN_ARTIKEL'
        reason = _non_article_reason(classification, normalized)
        include_in_article_sum = False
    return {
        'raw_line': line,
        'normalized_line': normalized,
        'store_name': store_name,
        'filename': filename,
        'classification': classification,
        'article_decision': article_decision,
        'include_in_article_sum': include_in_article_sum,
        'reason': reason,
        'extra_context': dict(extra_context or {}),
    }


def classification_allows_append(classification: str | None) -> bool:
    return classification not in BLOCKING_CLASSIFICATIONS
