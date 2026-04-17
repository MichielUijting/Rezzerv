from __future__ import annotations

import re
import unicodedata


def normalize_ocr_line(line: str) -> str:
    normalized = str(line or '').replace('|', ' ')
    normalized = normalized.replace('€', ' € ')
    normalized = re.sub(r'(?<=\d)[Oo](?=)', '0', normalized)
    normalized = re.sub(r'(?<=)[Oo](?=\d)', '0', normalized)
    normalized = re.sub(r'(?<=\d)\s*[.,]\s*(?=\d{2})', ',', normalized)
    normalized = re.sub(r'(?<=\d)\s+(?=\d{2})', ',', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def normalized_skip_text(line: str | None) -> str:
    lowered = normalize_ocr_line(str(line or '')).strip().lower()
    lowered = unicodedata.normalize('NFKD', lowered)
    lowered = ''.join(ch for ch in lowered if not unicodedata.combining(ch))
    lowered = re.sub(r'\s+', ' ', lowered)
    return lowered.strip()


def looks_like_ocr_noise_label(line: str) -> bool:
    normalized = normalized_skip_text(line)
    if not normalized:
        return True
    alpha_tokens = re.findall(r'[a-zà-ÿ]+', normalized)
    if not alpha_tokens:
        return True
    short_tokens = sum(1 for token in alpha_tokens if len(token) <= 2)
    long_tokens = sum(1 for token in alpha_tokens if len(token) >= 4)
    if len(alpha_tokens) >= 8 and short_tokens >= 5 and short_tokens > long_tokens:
        return True
    if len(alpha_tokens) >= 6 and re.search(r'(?:[a-z]{1,2}\s+){4,}', normalized):
        return True
    return False


def looks_like_multiplier_detail_label(line: str) -> bool:
    candidate = normalize_ocr_line(str(line or '')).strip()
    if not candidate:
        return False
    return bool(
        re.fullmatch(
            r"\d+(?:[\.,]\d+)?\s*[xX×]\s*-?\d{1,6}[,\.]\d{2}(?:\s+-?\d{1,6}[,\.]\d{2})?",
            candidate,
        )
    )


PRICE_RE = re.compile(r'-?\d{1,6}[\.,]\d{2}')
TOTAL_WORD_RE = re.compile(
    r'\b(?:totaal|total|subtotaal|subtotal|te betalen|betaling|betaald|pin|bankpas|kaart|contant|btw|wisselgeld|retourpin|pinbetaling|ideal|vpay|maestro)\b',
    re.IGNORECASE,
)


def extract_amount_tokens(line: str) -> list[str]:
    normalized = normalize_ocr_line(str(line or ''))
    return PRICE_RE.findall(normalized)


def has_amount(line: str) -> bool:
    return bool(extract_amount_tokens(line))


def extract_dominant_amount(line: str) -> str | None:
    amounts = extract_amount_tokens(line)
    if not amounts:
        return None
    return amounts[-1]


def _looks_like_contact_or_reference_line(lowered: str) -> bool:
    if re.search(r'https?://|www\.|@', lowered):
        return True
    if re.search(r'(?:tel|telefoon|klantenservice|contact|servicepunt|openingstijden|webshop|website)', lowered):
        return True
    if re.search(r'(?:ordernummer|bestelnummer|factuurnummer|transactie|terminal|merchant|auth|autorisatie|kaartnr|iban|kvk|btwnr)', lowered):
        return True
    if re.search(r'\d{4}\s?[a-z]{2}', lowered) and re.search(r'(?:straat|laan|weg|plein|markt|dreef|gld|arnhem|nijmegen|utrecht|amsterdam|rotterdam|eindhoven|tilburg)', lowered):
        return True
    return False


def _looks_like_discount_or_summary_line(lowered: str) -> bool:
    if re.match(r'^(?:\d+\s*[x×]\s*)?(?:actie|korting|bonus|voordeel|spaar|zegel)', lowered):
        return True
    if re.search(r'(?:uw voordeel|totaal voordeel|bij u bespaard|u bespaarde|korting|spaarpunten|koopzegel|bonus box|bonuskaart|klantenkaart)', lowered):
        return True
    return False


def _looks_like_payment_or_total_line(lowered: str, raw_line: str) -> bool:
    if any(token in lowered for token in (
        'totaal', 'subtotaal', 'te betalen', 'betaling', 'betaald', 'bedrag', 'contant', 'pin', 'bankpas', 'kaart',
        'btw', 'wisselgeld', 'retourpin', 'pinbetaling', 'ideal', 'vpay', 'maestro'
    )):
        return True
    if re.search(r'datum', lowered) and re.search(r'\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?', lowered):
        return True
    if re.search(r'\d{1,2}:\d{2}(?::\d{2})?', lowered) and re.search(r'\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?', lowered):
        return True
    if re.search(r'(?:contant|pin|bankpas|kaart)', lowered) and re.search(r'-?\d+[\.,]\d{2}', lowered):
        return True
    if re.fullmatch(r'(?:bedrag\s*=\s*euro|contant|pin|bankpas)\s*-?\d+[\.,]\d{2}', lowered):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}\s+\d', raw_line):
        return True
    return False


def should_skip_receipt_line(line: str) -> bool:
    lowered = normalized_skip_text(line)
    raw_line = str(line or '').strip()
    if not lowered:
        return True
    skip_markers = (
        'subtotaal', 'subtotal', 'uw voordeel', 'waarvan', 'bonus box', 'koopzegel', 'koopzegels',
        'totaal korting', 'prijsvoordeel', 'spaaractie', 'spaaracties', 'betaald met', 'bankpas', 'pinnen', 'vpay', 'actie ', 'korting',
        'betaling', 'auth.', 'autorisatie', 'merchant', 'terminal', 'transactie', 'kaartnr', 'kaart:',
        'contactloze', 'contactloos', 'klantticket', 'btw over', 'btw overzicht', 'bedr.excl', 'bedr.incl',
        'bedrag excl', 'bedrag incl', 'bedrag euro', 'bedrag = euro', 'filiaal informatie', 'aantal artikelen', 'aantal papieren',
        'openingstijden', 'dank u wel', 'aankoop gedaan bij', 'merchant ref', 'v-pay', 'maestro',
        'v pay', 'copy kaarthouder', 'kopie kaarthouder', 'akkoord', 'poi:', 'token', 'period', 'periode:',
        'u bent geholpen door', 'servicebalie', 'pluspunten', 'geeft meer voordeel', 'plus geeft meer voordeel', 'plus geeft neer voordeel', 'contant',
        'selfpay', 'the voice', 'datum:', 'actie bonduelle', 'store ', ' pos ', ' trans', 'smc =', 'acme', 'wisselgeld',
        'klantenkaart', 'bonuskaart', 'zegel', 'zegels', 'kassabon', 'kassa', 'pinbetaling', 'retourpin',
        'myaldi', 'bij u bespaard', 'digitale kassabon', 'spaarpunten', 'totaal voordeel', 'u bespaarde',
        'klantenservice', 'telefoon', 'website', 'webshop', 'ordernummer', 'bestelnummer', 'factuurnummer',
    )
    if any(marker in lowered for marker in skip_markers):
        return True
    if lowered.startswith(('bonus ', 'bbox ', 'korting ', 'retour ', 'refund ', 'contant ', 'pin ', 'bedrag ')):
        return True
    if lowered in {'contant', 'pin', 'bankpas', 'betaling', 'bedrag', 'bedrag = euro'}:
        return True
    if 'totaal' in lowered:
        return True
    if re.match(r'^(?:\d+%|%)', lowered):
        return True
    if _looks_like_contact_or_reference_line(lowered) or _looks_like_discount_or_summary_line(lowered) or _looks_like_payment_or_total_line(lowered, raw_line):
        return True
    return False


def looks_like_item_label_only(line: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(line or '')).strip()
    if not candidate or should_skip_receipt_line(candidate):
        return False
    if not re.search(r'[A-Za-z]', candidate):
        return False
    if re.search(r'\d+[\.,]\d{2}', candidate):
        return False
    return True


def classify_receipt_line(line: str) -> str:
    normalized = normalize_ocr_line(str(line or '')).strip()
    normalized = re.sub(r'^[^A-Za-z0-9]+', '', normalized).strip()
    normalized = re.sub(r'[^A-Za-z0-9]+$', '', normalized).strip()
    if not normalized:
        return 'META'
    if looks_like_multiplier_detail_label(normalized):
        return 'DETAIL'
    if should_skip_receipt_line(normalized):
        return 'META'
    if TOTAL_WORD_RE.search(normalized):
        return 'META'
    if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', normalized):
        return 'META'
    if looks_like_item_label_only(normalized):
        return 'ITEM_LABEL'
    if re.search(r'[A-Za-z]', normalized) and has_amount(normalized):
        return 'ITEM'
    return 'META'


def is_ocr_non_item_line(line: str) -> bool:
    lowered = normalized_skip_text(line)
    raw_line = str(line or '').strip()
    if not lowered:
        return True
    ignore_tokens = (
        'totaal', 'subtotaal', 'te betalen', 'betaling', 'betaald', 'bedrag', 'bedrag = euro', 'contant', 'pin', 'kaart',
        'btw', 'iban', 'bezorgadres', 'klantenservice', 'openingstijden', 'retour', 'wisselgeld', 'transactie',
        'factuur', 'ordernummer', 'bestelnummer', 'besteld op', 'artikelnummer', 'omschrijving', 'pagina ',
        'coolblue klantenservice', 'karwei klantenservice', 'mediamarkt klantenservice', 'bankpas', 'ideal',
        'u bent geholpen door', 'servicebalie', 'pluspunten', 'geeft meer voordeel', 'plus geeft meer voordeel', 'plus geeft neer voordeel', 'zegel', 'zegels',
        'selfpay', 'the voice', 'datum:', 'actie bonduelle', 'store ', ' pos ', ' trans', 'smc =', 'acme', 'kassa', 'kassabon',
        'bonuskaart', 'klantenkaart', 'myaldi', 'bij u bespaard', 'digitale kassabon', 'spaarpunten', 'totaal voordeel',
    )
    if any(token in lowered for token in ignore_tokens):
        return True
    if re.fullmatch(r'[\d\W]+', lowered):
        return True
    if _looks_like_contact_or_reference_line(lowered) or _looks_like_discount_or_summary_line(lowered) or _looks_like_payment_or_total_line(lowered, raw_line):
        return True
    if looks_like_ocr_noise_label(lowered):
        return True
    if looks_like_multiplier_detail_label(line):
        return False
    amounts = re.findall(r'-?\d+[\.,]\d{2}', lowered)
    if amounts:
        try:
            if any(abs(float(a.replace(',', '.'))) > 500 for a in amounts):
                return True
        except Exception:
            return True
    if re.search(r'(?:store|pos|trans|selfpay|acme|smc)', lowered):
        return True
    if re.match(r'^[A-Z]\s+\d{1,2}\s+\d', raw_line):
        return True
    return False


def classify_ocr_receipt_line(line: str) -> str:
    normalized = normalize_ocr_line(str(line or '')).strip()
    if not normalized:
        return 'META'
    if looks_like_multiplier_detail_label(normalized):
        return 'DETAIL'
    if should_skip_receipt_line(normalized):
        return 'META'
    if TOTAL_WORD_RE.search(normalized):
        return 'META'
    if looks_like_item_label_only(normalized):
        return 'ITEM_LABEL'
    if re.search(r'[A-Za-z]', normalized) and has_amount(normalized):
        return 'ITEM'
    return 'META'
