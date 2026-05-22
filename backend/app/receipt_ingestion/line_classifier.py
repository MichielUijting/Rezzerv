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


def _default_false(_: str) -> bool:
    return False


def _normalize_store(value: str | None) -> str:
    return ''.join(ch.lower() for ch in str(value or '') if ch.isalnum())


def _has_amount(value: str) -> bool:
    return bool(re.search(r'(?<!\d)-?\d+[\.,]\d{2}(?!\d)', value))


def _footer_or_metadata(lowered: str) -> str:
    if any(token in lowered for token in FOOTER_TOKENS):
        return 'footer_payment_tax'
    return 'metadata'


def _generic_non_article_classification(line: str) -> str | None:
    """Generic conservative non-article rules.

    R9-13: this function only blocks lines that are evidently not article-with-price
    candidates. It does not choose totals, compute status, or alter PO status rules.
    """
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return 'ignore'
    lowered = normalized.lower()
    upper = normalized.upper().replace(',', '.')

    if re.fullmatch(r'(?:ZA|ZO|ZON)\s+\d{1,2}\.\d{2}', upper):
        return 'metadata'
    if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', lowered):
        return 'metadata'
    if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*', lowered):
        return 'metadata'
    if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', normalized):
        return 'metadata'
    if any(day in lowered for day in DUTCH_DAY_TOKENS) and ('t/m' in lowered or ' tot ' in lowered):
        return 'metadata'

    if re.match(r'^[A-Z]\s+\d{1,2}[,.]\d{2}%\b', normalized.upper()):
        return 'footer_payment_tax'
    if re.fullmatch(r'(?:[a-z]\s*)?\d{1,2}[,.]\d{2}\s*%.*', lowered):
        return 'footer_payment_tax'
    if re.fullmatch(r'\d{1,4}[.]\d{2}', normalized) or re.fullmatch(r'\d{1,4},\d{2}', normalized):
        return 'footer_payment_tax'

    if any(token in lowered for token in GENERIC_PAYMENT_TOKENS):
        return 'footer_payment_tax'
    if any(token in lowered for token in GENERIC_TAX_TOKENS):
        return 'footer_payment_tax'
    if any(token in lowered for token in GENERIC_DEPOSIT_RETURN_TOKENS):
        return 'footer_payment_tax'
    if any(token in lowered for token in GENERIC_TOTAL_TOKENS):
        return 'footer_payment_tax'
    if any(token in lowered for token in GENERIC_DISCOUNT_TOKENS):
        return 'footer_payment_tax'
    if any(token in lowered for token in GENERIC_LOYALTY_TOKENS):
        return 'metadata'
    if any(token in lowered for token in GENERIC_METADATA_TOKENS) and not _has_amount(lowered):
        return 'metadata'

    return None


def _store_specific_non_article_classification(line: str, store_name: str | None = None, filename: str | None = None) -> str | None:
    """Conservative chain-specific non-article rules.

    R9-11B: only rules that are evidently not an article-with-price live here.
    These rules may exclude payment/footer/loyalty/metadata noise, but must not
    force totals, status or article counts.
    """
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not normalized:
        return 'ignore'
    lowered = normalized.lower()
    store_key = _normalize_store(store_name) or _normalize_store(filename)

    common_payment_footer_tokens = (
        'te betalen', 'totaal', 'subtotaal', 'totaal incl', 'btw', 'vat',
        'pin', 'bankpas', 'maestro', 'visa', 'mastercard', 'contactloos',
        'terminal', 'transactie', 'transactienr', 'betaling', 'betaald',
        'wisselgeld', 'kasbon', 'bonnr', 'bon nr', 'bonnummer', 'referentie',
    )
    if any(token in lowered for token in common_payment_footer_tokens):
        return _footer_or_metadata(lowered)

    if re.fullmatch(r'(?:[a-z]\s*)?\d{1,2}[,.]\d{2}\s*%.*', lowered):
        return 'footer_payment_tax'
    if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?', lowered):
        return 'metadata'
    if re.fullmatch(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*', lowered):
        return 'metadata'

    if 'aldi' in store_key:
        aldi_metadata_tokens = (
            'aldi', 'aldi markt', 'filiaal', 'welkom', 'klantbon', 'kassabon',
            'uw voordeel', 'bedankt', 'tot ziens', 'www.', 'kvk', 'iban', 'tel',
        )
        aldi_non_article_tokens = (
            'statiegeld retour', 'emballage retour', 'retour statiegeld',
            'saldo', 'kaart', 'autoriseert', 'autorisatie',
        )
        if any(token in lowered for token in aldi_non_article_tokens):
            return 'footer_payment_tax'
        if any(token in lowered for token in aldi_metadata_tokens):
            return 'metadata'

    if 'plus' in store_key:
        plus_loyalty_tokens = (
            'pluspunten', 'plus punten', 'digitale spaarkaart', 'spaarkaart',
            'klant:', 'klantnummer', 'koopzegels', 'zegels', 'zegel',
            'punten saldo', 'saldo punten', 'persoonlijke bonus',
        )
        plus_metadata_tokens = (
            'plus', 'bedankt', 'welkom', 'filiaal', 'kassabon', 'www.',
            'kvk', 'iban', 'tel', 'servicebalie', 'klantenservice',
        )
        if any(token in lowered for token in plus_loyalty_tokens):
            return 'metadata'
        if any(token in lowered for token in plus_metadata_tokens) and not re.search(r'\d+[,.]\d{2}', lowered):
            return 'metadata'

    return None


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
    normalized = re.sub(r'\s+', ' ', str(line or '')).strip()
    if len(normalized) < 2:
        return 'ignore'

    generic_non_article = _generic_non_article_classification(normalized)
    if generic_non_article is not None:
        return generic_non_article

    store_specific = _store_specific_non_article_classification(normalized, store_name=store_name, filename=filename)
    if store_specific is not None:
        return store_specific

    lowered = normalized.lower()

    should_skip = should_skip_receipt_line or _default_false
    if should_skip(normalized):
        return _footer_or_metadata(lowered)

    looks_non_product = looks_like_non_product_receipt_label or _default_false
    if looks_non_product(normalized):
        return _footer_or_metadata(lowered)

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

    R9-11A/R9-11B/R9-13 contract:
    - ARTIKEL_MET_PRIJS is a standalone product candidate with price.
    - GEEN_ARTIKEL is metadata/footer/payment/VAT/noise.
    - Supporting lines are diagnostic only and need parser context before they can
      become part of an article. This function does not set status or totals.
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
