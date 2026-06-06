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

import re
from collections.abc import Callable
from typing import Any

from app.receipt_ingestion.profiles.aldi import is_aldi_context, is_aldi_non_product_line

BLOCKING_CLASSIFICATIONS = {'ignore', 'metadata', 'footer_payment_tax'}
FOOTER_TOKENS = ('btw', 'vat', 'totaal', 'subtotaal', 'betaal', 'bankpas', 'pin', 'terminal', 'transactie')
DUTCH_DAY_TOKENS = ('maandag', 'dinsdag', 'woensdag', 'woernsdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag')
ARTICLE_CLASSIFICATIONS = {'product_candidate'}
NON_ARTICLE_CLASSIFICATIONS = {'ignore', 'metadata', 'footer_payment_tax'}
SUPPORTING_ARTICLE_CLASSIFICATIONS = {'amount_detail', 'continuation'}
LegacyLineCheck = Callable[[str], bool]

GENERIC_PAYMENT_TOKENS = (
    'te betalen', 'totaal te betalen', 'betaald', 'betaling', 'kaartbetaling',
    'pin', 'pinnen', 'bankpas', 'maestro', 'visa', 'mastercard', 'v pay', 'v-pay',
    'contactloos', 'contant', 'wisselgeld', 'terminal', 'transactie', 'transactienr',
    'autorisatie', 'akkoord', 'merchant', 'kopie kaarthouder', 'klantticket',
)
GENERIC_TOTAL_TOKENS = (
    'totaal', 'subtotaal', 'sub totaal', 'bedrag euro', 'bedrag = euro',
    'total', 'subtotal', 'incl. btw', 'incl btw', 'totaal incl',
)
GENERIC_TAX_TOKENS = (
    'btw', 'vat', 'biw', 'bedrag excl', 'bedr.excl', 'btw-bedrag',
    'netto', 'bruto', 'excl.', 'excl ', 'incl.', 'incl ',
)
GENERIC_DISCOUNT_TOKENS = (
    'korting', 'bonus', 'actie', 'prijsvoordeel', 'jouw voordeel', 'uw voordeel',
    'lidl plus korting', 'totaal korting', 'coupon', 'voucher', 'gratis',
)
GENERIC_LOYALTY_TOKENS = (
    'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'pluspunt',
    'spaar', 'spaarkaart', 'loyalty', 'bonuskaart', 'klantnummer', 'klant:',
    'digitale zegels', 'digitale spaarkaart', 'campagne', 'punten saldo', 'saldo punten',
)
GENERIC_METADATA_TOKENS = (
    'openingstijd', 'openingstijden', 'ma-vr', 'ma tm', 'ma t/m', 'periode',
    'filiaal', 'kassa', 'kassabon', 'bonnr', 'bon nr', 'bonnummer', 'referentie',
    'www.', 'http', 'kvk', 'iban', 'tel:', 'telefoon', 'servicebalie', 'klantenservice',
    'bedankt', 'welkom', 'tot ziens', 'bezoek ook', 'voorwaarden',
)
GENERIC_DEPOSIT_RETURN_TOKENS = (
    'statiegeld retour', 'retour statiegeld', 'emballage retour', 'fust retour',
)
PRICED_DISCOUNT_ARTICLE_TOKENS = (
    'korting', 'bonus', 'actie', 'prijsvoordeel', 'jouw voordeel', 'uw voordeel',
    'lidl plus korting', 'totaal korting',
)
PRICED_LOYALTY_ARTICLE_TOKENS = ('zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'pluspunt')
VALUE_LINE_LABEL_PATTERNS = (r'koopzegels?(?:\s+premium)?', r'pluspunten?')


def _default_false(_: str) -> bool:
    return False


def _normalize_store(value: str | None) -> str:
    return ''.join(ch.lower() for ch in str(value or '') if ch.isalnum())


def _has_amount(value: str) -> bool:
    return bool(re.search(r'(?<!\d)-?\d+[\.,]\d{2}(?!\d)', value))


def _is_value_line_label_without_amount(lowered: str) -> bool:
    normalized = re.sub(r'\s+', ' ', str(lowered or '').strip().lower())
    return any(re.fullmatch(pattern, normalized) for pattern in VALUE_LINE_LABEL_PATTERNS)


def _token_match(lowered: str, tokens: tuple[str, ...]) -> str | None:
    for token in tokens:
        if token in lowered:
            return token
    return None


def _priced_article_value_token(lowered: str) -> str | None:
    if not _has_amount(lowered):
        return None
    if _token_match(lowered, GENERIC_PAYMENT_TOKENS):
        return None
    if _token_match(lowered, GENERIC_TAX_TOKENS):
        return None
    if _token_match(lowered, GENERIC_DEPOSIT_RETURN_TOKENS):
        return None
    return _token_match(lowered, PRICED_LOYALTY_ARTICLE_TOKENS) or _token_match(lowered, PRICED_DISCOUNT_ARTICLE_TOKENS)


def _footer_or_metadata(lowered: str) -> str:
    if any(token in lowered for token in FOOTER_TOKENS):
        return 'footer_payment_tax'
    return 'metadata'


def _decision(classification: str, rule: str, matched: str | None = None, *, stage: str = 'generic') -> dict[str, Any]:
    return {'classification': classification, 'stage': stage, 'rule': rule, 'matched': matched}


def _generic_non_article_trace(line: str) -> dict[str, Any] | None:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return _decision('ignore', 'EMPTY_OR_WHITESPACE_LINE')
    lowered = normalized.lower()
    upper = normalized.upper().replace(',', '.')
    if _is_value_line_label_without_amount(lowered):
        return _decision('product_candidate', 'GENERIC_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION', normalized)
    if re.fullmatch(r'(?:ZA|ZO|ZON)\s+\d{1,2}\.\d{2}', upper):
        return _decision('metadata', 'GENERIC_REGEX_SHORT_DAY_TIME', normalized)
    if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', lowered):
        return _decision('metadata', 'GENERIC_REGEX_STANDALONE_TIME', normalized)
    if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*', lowered):
        return _decision('metadata', 'GENERIC_REGEX_DATE_PREFIX', normalized)
    if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
        return _decision('metadata', 'GENERIC_REGEX_DATE_ANYWHERE', normalized)
    if any(day in lowered for day in DUTCH_DAY_TOKENS) and ('t/m' in lowered or ' tot ' in lowered):
        return _decision('metadata', 'GENERIC_DUTCH_DAY_RANGE', _token_match(lowered, DUTCH_DAY_TOKENS))
    if re.match(r'^[A-Z]\s+\d{1,2}[,.]\d{2}%\b', normalized.upper()):
        return _decision('footer_payment_tax', 'GENERIC_REGEX_VAT_CODE_PERCENT', normalized)
    if re.fullmatch(r'(?:[a-z]\s*)?\d{1,2}[,.]\d{2}\s*%.*', lowered):
        return _decision('footer_payment_tax', 'GENERIC_REGEX_PERCENT_LINE', normalized)
    if re.fullmatch(r'\d{1,4}[.]\d{2}', normalized) or re.fullmatch(r'\d{1,4},\d{2}', normalized):
        return _decision('footer_payment_tax', 'GENERIC_REGEX_STANDALONE_AMOUNT', normalized)
    for tokens, classification, rule in (
        (GENERIC_PAYMENT_TOKENS, 'footer_payment_tax', 'GENERIC_PAYMENT_TOKENS'),
        (GENERIC_TAX_TOKENS, 'footer_payment_tax', 'GENERIC_TAX_TOKENS'),
        (GENERIC_DEPOSIT_RETURN_TOKENS, 'footer_payment_tax', 'GENERIC_DEPOSIT_RETURN_TOKENS'),
    ):
        token = _token_match(lowered, tokens)
        if token:
            return _decision(classification, rule, token)
    token = _priced_article_value_token(lowered)
    if token:
        return _decision('product_candidate', 'GENERIC_PRICED_DISCOUNT_OR_LOYALTY_LINE', token)
    for tokens, classification, rule in (
        (GENERIC_TOTAL_TOKENS, 'footer_payment_tax', 'GENERIC_TOTAL_TOKENS'),
        (GENERIC_DISCOUNT_TOKENS, 'footer_payment_tax', 'GENERIC_DISCOUNT_TOKENS'),
        (GENERIC_LOYALTY_TOKENS, 'metadata', 'GENERIC_LOYALTY_TOKENS'),
    ):
        token = _token_match(lowered, tokens)
        if token:
            return _decision(classification, rule, token)
    token = _token_match(lowered, GENERIC_METADATA_TOKENS)
    if token and not _has_amount(lowered):
        return _decision('metadata', 'GENERIC_METADATA_TOKENS_NO_AMOUNT', token)
    return None


def _generic_non_article_classification(line: str) -> str | None:
    decision = _generic_non_article_trace(line)
    return str(decision.get('classification')) if decision else None


def _store_specific_non_article_trace(line: str, store_name: str | None = None, filename: str | None = None) -> dict[str, Any] | None:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return _decision('ignore', 'EMPTY_OR_WHITESPACE_LINE', stage='store_specific')
    lowered = normalized.lower()
    store_key = _normalize_store(store_name) or _normalize_store(filename)
    if _is_value_line_label_without_amount(lowered):
        return _decision('product_candidate', 'STORE_VALUE_LINE_LABEL_FROM_SAVINGS_ACTION', normalized, stage='store_specific')
    common_payment_footer_tokens = (
        'te betalen', 'totaal', 'subtotaal', 'totaal incl', 'btw', 'vat',
        'pin', 'bankpas', 'maestro', 'visa', 'mastercard', 'contactloos',
        'terminal', 'transactie', 'transactienr', 'betaling', 'betaald',
        'wisselgeld', 'kasbon', 'bonnr', 'bon nr', 'bonnummer', 'referentie',
    )
    token = _token_match(lowered, common_payment_footer_tokens)
    if token:
        return _decision(_footer_or_metadata(lowered), 'STORE_COMMON_PAYMENT_FOOTER_TOKENS', token, stage='store_specific')
    if re.fullmatch(r'(?:[a-z]\s*)?\d{1,2}[,.]\d{2}\s*%.*', lowered):
        return _decision('footer_payment_tax', 'STORE_REGEX_PERCENT_LINE', normalized, stage='store_specific')
    if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', lowered):
        return _decision('metadata', 'STORE_REGEX_STANDALONE_TIME', normalized, stage='store_specific')
    if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*', lowered):
        return _decision('metadata', 'STORE_REGEX_DATE_PREFIX', normalized, stage='store_specific')
    if is_aldi_context(store_name, filename) or 'aldi' in store_key:
        if is_aldi_non_product_line(normalized):
            return _decision('metadata', 'ALDI_FRAME_NON_PRODUCT_LINE', normalized, stage='store_specific')
        token = _token_match(lowered, ('statiegeld retour', 'emballage retour', 'retour statiegeld', 'saldo', 'kaart', 'autoriseert', 'autorisatie'))
        if token:
            return _decision('footer_payment_tax', 'ALDI_NON_ARTICLE_TOKENS', token, stage='store_specific')
        token = _token_match(lowered, ('aldi', 'aldi markt', 'filiaal', 'welkom', 'klantbon', 'kassabon', 'uw voordeel', 'bedankt', 'tot ziens', 'www.', 'kvk', 'iban', 'tel'))
        if token:
            return _decision('metadata', 'ALDI_METADATA_TOKENS', token, stage='store_specific')
    if 'plus' in store_key:
        token = _priced_article_value_token(lowered)
        if token:
            return _decision('product_candidate', 'PLUS_PRICED_DISCOUNT_OR_LOYALTY_LINE', token, stage='store_specific')
        token = _token_match(lowered, ('pluspunten', 'plus punten', 'digitale spaarkaart', 'spaarkaart', 'klant:', 'klantnummer', 'koopzegels', 'zegels', 'zegel', 'punten saldo', 'saldo punten', 'persoonlijke bonus'))
        if token:
            return _decision('metadata', 'PLUS_LOYALTY_TOKENS', token, stage='store_specific')
        token = _token_match(lowered, ('plus', 'bedankt', 'welkom', 'filiaal', 'kassabon', 'www.', 'kvk', 'iban', 'tel', 'servicebalie', 'klantenservice'))
        if token and not re.search(r'\d+[,.]\d{2}', lowered):
            return _decision('metadata', 'PLUS_METADATA_TOKENS_NO_AMOUNT', token, stage='store_specific')
    return None


def _store_specific_non_article_classification(line: str, store_name: str | None = None, filename: str | None = None) -> str | None:
    decision = _store_specific_non_article_trace(line, store_name=store_name, filename=filename)
    return str(decision.get('classification')) if decision else None


def _non_article_reason(classification: str | None, line: str) -> str:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    lowered = normalized.lower()
    if classification == 'footer_payment_tax':
        if any(token in lowered for token in ('totaal', 'subtotaal')):
            return 'total_or_subtotal_line'
        if any(token in lowered for token in ('btw', 'vat', 'biw', 'netto', 'bruto')):
            return 'vat_line'
        if any(token in lowered for token in ('betaal', 'bankpas', 'pin', 'terminal', 'transactie', 'maestro', 'visa', 'mastercard')):
            return 'payment_line'
        if any(token in lowered for token in ('statiegeld retour', 'retour statiegeld', 'emballage retour')):
            return 'deposit_return_or_refund_line'
        if any(token in lowered for token in ('korting', 'bonus', 'actie', 'prijsvoordeel', 'voordeel', 'coupon')):
            return 'discount_or_promotion_line'
        if re.fullmatch(r'\d{1,4}[.,]\d{2}', normalized):
            return 'standalone_amount_line'
        return 'footer_payment_tax_line'
    if classification == 'metadata':
        if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
            return 'date_or_time_metadata'
        if any(day in lowered for day in DUTCH_DAY_TOKENS):
            return 'date_or_period_metadata'
        if any(token in lowered for token in ('pluspunten', 'spaarkaart', 'koopzegel', 'klantnummer', 'zegels', 'bonuskaart')):
            return 'loyalty_or_savings_metadata'
        return 'receipt_metadata'
    if classification == 'ignore':
        return 'noise_or_unclassified_line'
    if classification == 'amount_detail':
        return 'supporting_amount_detail_not_standalone_article'
    if classification == 'continuation':
        return 'label_continuation_needs_article_context'
    return 'unknown_classification'


def trace_receipt_text_line_classification(
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
) -> dict[str, Any]:
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if len(normalized) < 2:
        return _decision('ignore', 'TOO_SHORT_LINE', normalized, stage='precheck')
    generic_non_article = _generic_non_article_trace(normalized)
    if generic_non_article is not None:
        return generic_non_article
    store_specific = _store_specific_non_article_trace(normalized, store_name=store_name, filename=filename)
    if store_specific is not None:
        return store_specific
    lowered = normalized.lower()
    should_skip = should_skip_receipt_line or _default_false
    if should_skip(normalized):
        return _decision(_footer_or_metadata(lowered), 'LEGACY_SHOULD_SKIP_RECEIPT_LINE', normalized, stage='legacy_callback')
    looks_non_product = looks_like_non_product_receipt_label or _default_false
    if looks_non_product(normalized):
        return _decision(_footer_or_metadata(lowered), 'LEGACY_LOOKS_LIKE_NON_PRODUCT_LABEL', normalized, stage='legacy_callback')
    if detail_only_re is not None and detail_only_re.match(normalized):
        return _decision('amount_detail', 'DETAIL_ONLY_RE', normalized, stage='parser_regex')
    if qty_first_re is not None and qty_first_re.match(normalized):
        return _decision('product_candidate', 'QTY_FIRST_RE', normalized, stage='parser_regex')
    if label_first_re is not None and label_first_re.match(normalized):
        return _decision('product_candidate', 'LABEL_FIRST_RE', normalized, stage='parser_regex')
    looks_item_label = looks_like_item_label_only or _default_false
    if looks_item_label(normalized):
        return _decision('continuation', 'LEGACY_LOOKS_LIKE_ITEM_LABEL_ONLY', normalized, stage='legacy_callback')
    return _decision('ignore', 'NO_RULE_MATCHED', normalized, stage='fallback')


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
    decision = trace_receipt_text_line_classification(
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
    return str(decision.get('classification') or 'ignore')


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
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    trace = trace_receipt_text_line_classification(
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
    classification = str(trace.get('classification') or 'ignore')
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
        'rule': trace.get('rule'),
        'stage': trace.get('stage'),
        'matched': trace.get('matched'),
        'trace': trace,
        'extra_context': dict(extra_context or {}),
    }


def classification_allows_append(classification: str | None) -> bool:
    return classification not in BLOCKING_CLASSIFICATIONS
