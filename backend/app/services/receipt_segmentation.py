from __future__ import annotations

import re
from typing import Any

ANY_PRICE_RE = re.compile(r'[-+]?\d{1,4}(?:[.,]\d{2})')
ONLY_PRICE_RE = re.compile(r'^\s*[-+]?\d{1,4}(?:[.,]\d{2})\s*$')

TOTAL_KEYWORDS = {
    'totaal', 'subtotaal', 'subtotal', 'te betalen', 'betaling', 'betaald', 'retour', 'wisselgeld', 'saldo'
}
PAYMENT_KEYWORDS = {
    'pin', 'kaart', 'maestro', 'mastercard', 'visa', 'v-pay', 'terminal', 'merchant', 'nfc', 'autorisatie',
    'transactie', 'kaartnummer', 'kaartserienummer', 'aid', 'contactloos', 'contant', 'cash', 'debet'
}
FOOTER_KEYWORDS = {
    'bedankt', 'openingstijden', 'openingstijd', 'klantenservice', 'www.', '.nl', 'facebook', 'instagram',
    'spaar', 'zegel', 'zegels', 'punten', 'bonuskaart', 'bonus', 'koopzegel', 'uw voordeel', 'voordeel'
}
NOISE_KEYWORDS = {
    'btw', 'belasting', 'kassa', 'filiaal', 'adres', 'pin', 'terminal', 'merchant', 'transactie',
    'kaart', 'autorisatie', 'nfc', 'v-pay', 'maestro', 'mastercard', 'visa', 'zegel', 'zegels',
    'punten', 'koopzegel', 'bonus', 'voordeel', 'openingstijden', 'openingstijd'
}


def _norm(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '').strip().lower())


def _has_price(text: str) -> bool:
    return bool(ANY_PRICE_RE.search(text))


def _is_only_amount(text: str) -> bool:
    return bool(ONLY_PRICE_RE.match(text.replace(' ', '')))


def _looks_like_header(text: str) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False
    if any(store in normalized for store in ('albert heijn', 'jumbo', 'plus', 'aldi', 'lidl', 'picnic')):
        return True
    if re.search(r'\b\d{1,2}[:.]\d{2}\b', normalized):
        return True
    if re.search(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', normalized):
        return True
    if re.search(r'\b\d{4}\s?[a-z]{2}\b', normalized):
        return True
    return False


def _looks_like_total(text: str) -> bool:
    normalized = _norm(text)
    return any(keyword in normalized for keyword in TOTAL_KEYWORDS)


def _looks_like_payment(text: str) -> bool:
    normalized = _norm(text)
    return any(keyword in normalized for keyword in PAYMENT_KEYWORDS)


def _looks_like_footer(text: str) -> bool:
    normalized = _norm(text)
    return any(keyword in normalized for keyword in FOOTER_KEYWORDS)


def _looks_like_article(text: str) -> bool:
    normalized = _norm(text)
    if not normalized:
        return False
    if _is_only_amount(normalized):
        return False
    if len(normalized) > 90:
        return False
    if any(keyword in normalized for keyword in NOISE_KEYWORDS):
        return 'gratis' in normalized and _has_price(normalized)
    if not re.search(r'[a-zA-Z]', normalized):
        return False
    if _has_price(normalized):
        return True
    return 2 <= len(normalized.split()) <= 6 and len(normalized) <= 42


def segment_receipt_blocks(ocr_lines: list[str]) -> dict[str, Any]:
    cleaned_lines = [re.sub(r'\s+', ' ', str(line or '').strip()) for line in ocr_lines if str(line or '').strip()]
    if not cleaned_lines:
        return {
            'header_lines': [],
            'article_lines': [],
            'total_lines': [],
            'payment_lines': [],
            'footer_lines': [],
            'debug': {'input_count': 0, 'article_count': 0, 'dropped_from_articles': []},
        }

    header_cutoff = max(2, int(len(cleaned_lines) * 0.18))
    footer_start = int(len(cleaned_lines) * 0.82)

    header_lines: list[str] = []
    article_lines: list[str] = []
    total_lines: list[str] = []
    payment_lines: list[str] = []
    footer_lines: list[str] = []

    for pos, line in enumerate(cleaned_lines):
        if _looks_like_total(line):
            total_lines.append(line)
            continue
        if _looks_like_payment(line):
            payment_lines.append(line)
            continue
        if pos < header_cutoff and _looks_like_header(line):
            header_lines.append(line)
            continue
        if pos >= footer_start and _looks_like_footer(line):
            footer_lines.append(line)
            continue
        if _looks_like_footer(line):
            footer_lines.append(line)
            continue
        if _looks_like_article(line):
            article_lines.append(line)
            continue
        if pos < header_cutoff:
            header_lines.append(line)
        elif pos >= footer_start:
            footer_lines.append(line)
        else:
            payment_lines.append(line)

    cleaned_articles: list[str] = []
    dropped_from_articles: list[dict[str, str]] = []
    for line in article_lines:
        normalized = _norm(line)
        if _is_only_amount(normalized):
            dropped_from_articles.append({'reason': 'only_amount', 'text': line})
            continue
        if len(normalized) > 90:
            dropped_from_articles.append({'reason': 'too_long', 'text': line})
            continue
        if any(keyword in normalized for keyword in NOISE_KEYWORDS) and not ('gratis' in normalized and _has_price(normalized)):
            dropped_from_articles.append({'reason': 'noise_keyword', 'text': line})
            continue
        cleaned_articles.append(line)

    return {
        'header_lines': header_lines,
        'article_lines': cleaned_articles,
        'total_lines': total_lines,
        'payment_lines': payment_lines,
        'footer_lines': footer_lines,
        'debug': {
            'input_count': len(cleaned_lines),
            'header_count': len(header_lines),
            'article_count': len(cleaned_articles),
            'total_count': len(total_lines),
            'payment_count': len(payment_lines),
            'footer_count': len(footer_lines),
            'dropped_from_articles': dropped_from_articles[:25],
        },
    }
