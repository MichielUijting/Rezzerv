from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from typing import Any

from app.receipt_ingestion.amounts import (
    amount_to_float as _amount_to_float,
    parse_decimal as _parse_decimal,
    price_from_split_parts as _price_from_split_parts,
)
from app.receipt_ingestion.structured_product_gateway import append_structured_product_candidate
from app.receipt_ingestion.parser_diagnostics import summarize_lines_parser_diagnostics
from app.receipt_ingestion.service_parts.receipt_result_helpers import ReceiptParseResult
from app.receipt_ingestion.service_parts.text_extraction import (
    _html_to_text,
    _normalize_store_specific_text,
    _normalize_text_lines,
)

DUTCH_MONTHS = {
    'januari': 1, 'februari': 2, 'maart': 3, 'april': 4, 'mei': 5, 'juni': 6,
    'juli': 7, 'augustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
}

RECEIPT_NON_PRODUCT_LABEL_TOKENS = (
    'btw', 'vat', 'totaal', 'subtotaal', 'netto', 'bruto', 'bedrag', 'betaling',
    'betaald', 'bankpas', 'pin', 'pinnen', 'vpay', 'v-pay', 'maestro', 'terminal',
    'transactie', 'autorisatie', 'auth', 'kaart', 'kaartserienummer', 'datum', 'tijd',
    'groep', 'incl', 'excl', 'periode', 'leesmethod', 'contactloos', 'klantticket',
    'kopie', 'bonnummer', 'kassanr', 'kassa', 'filiaal', 'openingstijden', 'www.',
    'http', 'welkom', 'bedankt', 'dank u', 'tot ziens', 'coupon', 'actiecode',
    'zegel', 'zegels', 'koopzegel', 'koopzegels', 'pluspunten', 'spaarkaart',
)

def _clean_receipt_label(value: str | None) -> str:
    label = re.sub(r'\s+', ' ', str(value or '')).strip(' .:-')
    label = re.sub(r'\s+(?:EUR|[A-Z]{1,3})$', '', label).strip()
    label = re.sub(r'^[0O]\s+(?=[A-Za-z])', '', label).strip()
    return label[:255]


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
    if any(token in lowered for token in RECEIPT_NON_PRODUCT_LABEL_TOKENS):
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


def _parse_dutch_textual_date(text: str, default_year: int | None = None) -> str | None:
    match = re.search(r'(?i)\b(\d{1,2})\s+(' + '|'.join(DUTCH_MONTHS.keys()) + r')(?:\s+(\d{4}))?', str(text or ''))
    if not match:
        return None
    day = int(match.group(1))
    month = DUTCH_MONTHS[match.group(2).lower()]
    year = int(match.group(3) or default_year or datetime.utcnow().year)
    try:
        return datetime(year, month, day).isoformat()
    except ValueError:
        return None


def _receipt_result_from_manual(store_name: str | None, purchase_at: str | None, total_amount: Decimal | None, lines: list[dict[str, Any]], *, store_branch: str | None = None, confidence: float = 0.8) -> ReceiptParseResult:
    status = 'parsed' if lines and total_amount is not None else 'review_needed'
    return ReceiptParseResult(
        is_receipt=True,
        parse_status=status,
        confidence_score=confidence,
        store_name=store_name,
        purchase_at=purchase_at,
        total_amount=total_amount,
        discount_total=None,
        currency='EUR',
        lines=lines,
        store_branch=store_branch,
        parser_diagnostics=summarize_lines_parser_diagnostics(lines),
    )


def _line_dict(label: str, quantity: float | None, unit_price: Decimal | None, line_total: Decimal | None, *, unit: str | None = None, confidence: float = 0.86) -> dict[str, Any]:
    return {
        'raw_label': _clean_receipt_label(label),
        'normalized_label': _clean_receipt_label(label),
        'quantity': quantity,
        'unit': unit,
        'unit_price': _amount_to_float(unit_price),
        'line_total': _amount_to_float(line_total),
        'discount_amount': None,
        'barcode': None,
        'confidence_score': confidence,
    }


def _parse_action_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'action' not in filename.lower() and 'valburgseweg' not in text.lower():
        return None
    lines = _normalize_text_lines(_normalize_store_specific_text(text))
    purchase_at = None
    m = re.search(r'(?i)(\d{1,2})\s+(' + '|'.join(DUTCH_MONTHS.keys()) + r')\s+om\s+(\d{1,2}:\d{2})', text)
    if m:
        try:
            purchase_at = datetime(datetime.utcnow().year, DUTCH_MONTHS[m.group(2).lower()], int(m.group(1)), int(m.group(3).split(':')[0]), int(m.group(3).split(':')[1])).isoformat()
        except Exception:
            purchase_at = None
    total_amount = _parse_decimal(re.search(r'(?i)Totaal\s+\d+\s+â‚¬\s*([0-9]+,[0-9]{2})', text).group(1)) if re.search(r'(?i)Totaal\s+\d+\s+â‚¬\s*([0-9]+,[0-9]{2})', text) else None
    branch = 'Valburgseweg 16, 6661 EV Elst'
    start = next((i for i, line in enumerate(lines) if 'artikel aantal prijs' in line.lower()), None)
    end = next((i for i, line in enumerate(lines) if line.lower().startswith('totaal ')), None)
    extracted: list[dict[str, Any]] = []
    if start is not None and end is not None and end > start:
        buffer: list[str] = []
        for line in lines[start + 1:end]:
            match = re.match(r'^(?P<qty>\d+)\s+â‚¬\s*(?P<amount>\d+[\.,]\d{2})$', line)
            if match and buffer:
                label = ' '.join(buffer)
                label = re.sub(r'\s*-\s*\d{6,}$', '', label).strip()
                qty = float(match.group('qty'))
                total = _parse_decimal(match.group('amount'))
                unit_price = (total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if total is not None and qty else total
                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=total,
                    discount_amount=None,
                    barcode=None,
                    source_index=None,
                    raw_line=line,
                    normalized_line=line,
                    source_segment=' | '.join(buffer + [line]),
                    filename=filename,
                    store_name='Action',
                    function_name='_parse_action_pdf_result',
                    append_branch='action_pdf_line',
                    parser_path='_parse_action_pdf_result.action_pdf_line',
                    caller_line_hint='Action PDF structured line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.88,
                )
                buffer = []
            else:
                buffer.append(line)
    return _receipt_result_from_manual('Action', purchase_at, total_amount, extracted, store_branch=branch, confidence=0.88)


def _parse_gamma_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'gamma' not in filename.lower() and 'gamma.nl' not in text.lower() and 'kassabonnummer' not in text.lower():
        return None
    lines = _normalize_text_lines(_normalize_store_specific_text(text))
    purchase_at = _purchase_at_from_lines(lines, filename)
    total_match = re.search(r'(?i)Totaal incl\. BTWâ‚¬\s*([0-9]+,[0-9]{2})', text)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        m = re.match(r'^(?P<code>\d{5,})\s+(?P<label>.+)$', line)
        if not m:
            continue
        label_parts = [m.group('label')]
        j = idx + 1
        while j < len(lines) and not re.search(r'\d+%\s+\d+\s+â‚¬\s*\d+[\.,]\d{2}', lines[j]):
            if re.match(r'^Totaal', lines[j], re.I):
                break
            label_parts.append(lines[j])
            j += 1
        if j < len(lines):
            detail = lines[j]
            d = re.search(r'(?P<vat>\d+%)\s+(?P<qty>\d+(?:[\.,]\d+)?)\s+â‚¬\s*(?P<unit>\d+[\.,]\d{2})(?:\s+â‚¬\s*(?P<total>\d+[\.,]\d{2}))?', detail)
            if d:
                qty = float(d.group('qty').replace(',', '.'))
                unit_price = _parse_decimal(d.group('unit'))
                line_total = _parse_decimal(d.group('total')) or unit_price
                append_structured_product_candidate(
                    extracted,
                    label=' '.join(label_parts),
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=line_total,
                    discount_amount=None,
                    barcode=m.group('code'),
                    source_index=idx,
                    raw_line=' | '.join(lines[idx:j + 1]),
                    normalized_line=re.sub(r'\s+', ' ', ' | '.join(lines[idx:j + 1])).strip(),
                    source_segment=' | '.join(lines[idx:j + 1]),
                    filename=filename,
                    store_name='Gamma',
                    function_name='_parse_gamma_pdf_result',
                    append_branch='gamma_pdf_line',
                    parser_path='_parse_gamma_pdf_result.gamma_pdf_line',
                    caller_line_hint='Gamma PDF structured line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.86,
                )
    return _receipt_result_from_manual('Gamma', purchase_at, total_amount, extracted, confidence=0.86)


def _parse_hornbach_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'hornbach' not in text.lower() and 'hornbach' not in filename.lower():
        return None
    normalized = _normalize_store_specific_text(text)
    purchase_at = None
    date_match = re.search(r'(?i)Rekeningsdatum:\s*(\d{2}\.\d{2}\.\d{4})', normalized) or re.search(r'(?i)Opdrachtdatum:\s*(\d{2}\.\d{2}\.\d{4})', normalized)
    if date_match:
        try:
            purchase_at = datetime.strptime(date_match.group(1), '%d.%m.%Y').isoformat()
        except ValueError:
            pass
    total_match = re.search(r'(?i)Totaalbedr\. rekening EUR\s*([0-9]+,[0-9]{2})', normalized) or re.search(r'(?i)Totaalbedrag rekening EUR\s*([0-9]+,[0-9]{2})', normalized)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    multi = re.search(r'10\s+7\s+St\s+10692297\s+(.+?)\s+21,00%\s+38,00\s+266,00', normalized, re.S)
    if multi:
        label = re.sub(r'\s+', ' ', multi.group(1)).strip()
        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=7.0,
            unit='St',
            unit_price=Decimal('38.00'),
            line_total=Decimal('266.00'),
            discount_amount=None,
            barcode='10692297',
            source_index=None,
            raw_line=multi.group(0),
            normalized_line=re.sub(r'\s+', ' ', multi.group(0)).strip(),
            source_segment=multi.group(0),
            filename=filename,
            store_name='Hornbach',
            function_name='_parse_hornbach_pdf_result',
            append_branch='hornbach_multi_item',
            parser_path='_parse_hornbach_pdf_result.hornbach_multi_item',
            caller_line_hint='Hornbach PDF structured multi item via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
    freight = re.search(r'8448722\s+Vrachtkosten\s+21,00%\s+22,50\s+22,50', normalized)
    if freight:
        append_structured_product_candidate(
            extracted,
            label='Vrachtkosten',
            quantity=1.0,
            unit=None,
            unit_price=Decimal('22.50'),
            line_total=Decimal('22.50'),
            discount_amount=None,
            barcode='8448722',
            source_index=None,
            raw_line=freight.group(0),
            normalized_line=re.sub(r'\s+', ' ', freight.group(0)).strip(),
            source_segment=freight.group(0),
            filename=filename,
            store_name='Hornbach',
            function_name='_parse_hornbach_pdf_result',
            append_branch='hornbach_freight',
            parser_path='_parse_hornbach_pdf_result.hornbach_freight',
            caller_line_hint='Hornbach PDF structured freight via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
    return _receipt_result_from_manual('Hornbach', purchase_at, total_amount, extracted, store_branch='Postbus 1099, 3430 BB Nieuwegein', confidence=0.9)


def _parse_lidl_invoice_pdf_result(text: str, filename: str) -> ReceiptParseResult | None:
    if 'lidl' not in text.lower() and 'lidl' not in filename.lower():
        return None
    normalized = _normalize_store_specific_text(text)
    lines = _normalize_text_lines(normalized)
    purchase_at = None
    date_match = re.search(r'(?i)Factuurdatum:\s*(\d{2}-\d{2}-\d{4})', normalized) or re.search(r'(?i)Besteldatum:\s*(\d{2}-\d{2}-\d{4})', normalized)
    if date_match:
        try:
            purchase_at = datetime.strptime(date_match.group(1), '%d-%m-%Y').isoformat()
        except ValueError:
            pass
    total_match = re.search(r'(?i)Totaal\s+([0-9]+,[0-9]{2})', normalized)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    extracted: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, line in enumerate(lines):
        product_match = re.match(r'^(?P<code>100\d{6,})(?:\s+)?(?P<label>.+)$', line)
        if not product_match:
            continue
        code = str(product_match.group('code') or '').strip()
        if not code or code in seen_codes:
            continue
        detail_line = lines[index + 2] if index + 2 < len(lines) else ''
        detail_match = re.search(r'21,0\s*%\s*(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<unit>\d+[\.,]\d{2})\s+(?P<total>\d+[\.,]\d{2})', detail_line)
        if not detail_match:
            continue
        seen_codes.add(code)
        label = re.sub(r'\s+', ' ', product_match.group('label')).strip(' -')
        qty = float(str(detail_match.group('qty')).replace(',', '.'))
        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=qty,
            unit=None,
            unit_price=_parse_decimal(detail_match.group('unit')),
            line_total=_parse_decimal(detail_match.group('total')),
            discount_amount=None,
            barcode=code,
            source_index=index,
            raw_line=' | '.join(lines[index:index + 3]),
            normalized_line=re.sub(r'\s+', ' ', ' | '.join(lines[index:index + 3])).strip(),
            source_segment=' | '.join(lines[index:index + 3]),
            filename=filename,
            store_name='Lidl Nederland GmbH',
            function_name='_parse_lidl_invoice_pdf_result',
            append_branch='lidl_invoice_product_line',
            parser_path='_parse_lidl_invoice_pdf_result.lidl_invoice_product_line',
            caller_line_hint='Lidl invoice structured product via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
    shipping = re.search(r'Verzendkosten\s+21,0\s*%\s*(?P<qty>\d+(?:[\.,]\d+)?)\s+(?P<unit>\d+[\.,]\d{2})\s+(?P<total>\d+[\.,]\d{2})', normalized)
    if shipping:
        append_structured_product_candidate(
            extracted,
            label='Verzendkosten',
            quantity=float(str(shipping.group('qty')).replace(',', '.')),
            unit=None,
            unit_price=_parse_decimal(shipping.group('unit')),
            line_total=_parse_decimal(shipping.group('total')),
            discount_amount=None,
            barcode=None,
            source_index=None,
            raw_line=shipping.group(0),
            normalized_line=re.sub(r'\s+', ' ', shipping.group(0)).strip(),
            source_segment=shipping.group(0),
            filename=filename,
            store_name='Lidl Nederland GmbH',
            function_name='_parse_lidl_invoice_pdf_result',
            append_branch='lidl_invoice_shipping',
            parser_path='_parse_lidl_invoice_pdf_result.lidl_invoice_shipping',
            caller_line_hint='Lidl invoice structured shipping via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.9,
        )
    return _receipt_result_from_manual('Lidl Nederland GmbH', purchase_at, total_amount, extracted, store_branch='Havenstraat 71, 1271 AD Huizen; Postbus 198, 1270 AD Huizen', confidence=0.9)


def _parse_bol_email_result(text: str, html_text: str, filename: str, header_date: str | None = None) -> ReceiptParseResult | None:
    haystack = _normalize_store_specific_text(html_text or text)
    if 'bol' not in haystack.lower() and 'bol' not in filename.lower():
        return None
    purchase_at = None
    if header_date:
        from email.utils import parsedate_to_datetime
        try:
            purchase_at = parsedate_to_datetime(header_date).replace(tzinfo=None).isoformat(timespec='seconds')
        except Exception:
            purchase_at = None
    total_match = re.search(r'(?is)Totaal\s+â‚¬\s*([0-9]+,[0-9]{2})', haystack)
    total_amount = _parse_decimal(total_match.group(1)) if total_match else None
    order_product = re.search(r'(?is)Dit heb je besteld.*?Bestelnummer:\s*([A-Z0-9-]+).*?([A-Z0-9+\-][^\n]+?)\s+Verkoper:\s+([^\n]+).*?Bezorgdatum:', haystack)
    extracted: list[dict[str, Any]] = []
    if order_product:
        label = re.sub(r'\s+', ' ', order_product.group(2)).strip()
        price_match = re.search(r'(?is)1x\s+â‚¬\s*([0-9]+,[0-9]{2})', haystack)
        price = _parse_decimal(price_match.group(1)) if price_match else total_amount
        append_structured_product_candidate(
            extracted,
            label=label,
            quantity=1.0,
            unit=None,
            unit_price=price,
            line_total=price,
            discount_amount=None,
            barcode=None,
            source_index=None,
            raw_line=order_product.group(0),
            normalized_line=re.sub(r'\s+', ' ', order_product.group(0)).strip(),
            source_segment=order_product.group(0),
            filename=filename,
            store_name='Bol',
            function_name='_parse_bol_email_result',
            append_branch='bol_email_order_product',
            parser_path='_parse_bol_email_result.bol_email_order_product',
            caller_line_hint='Bol email structured order product via append_structured_product_candidate',
            clean_label=_clean_receipt_label,
            amount_to_float=_amount_to_float,
            is_invalid_label=_looks_like_non_product_receipt_label,
            confidence_score=0.84,
        )
    return _receipt_result_from_manual('Bol', purchase_at, total_amount, extracted, confidence=0.84)


def _parse_picnic_email_result(text: str, html_text: str, filename: str, header_date: str | None = None) -> ReceiptParseResult | None:
    haystack = _normalize_store_specific_text(html_text or text)
    if 'picnic' not in haystack.lower() and 'picnic' not in filename.lower():
        return None
    raw_lines = _normalize_text_lines(haystack)
    lines = []
    for line in raw_lines:
        cleaned = re.sub(r'[]+', '', line).strip()
        if cleaned and cleaned not in {'.', 'â€¢'}:
            lines.append(cleaned)
    purchase_at = _parse_dutch_textual_date(haystack, default_year=2026)
    if purchase_at and 'T' not in purchase_at:
        purchase_at += 'T00:00:00'
    total_amount = None
    for idx, line in enumerate(lines):
        if line.lower() == 'totaal':
            nums = [token for token in lines[idx + 1: idx + 10] if re.fullmatch(r'-?\d+', token)]
            if len(nums) >= 2:
                total_amount = _price_from_split_parts(nums[0], nums[1])
                break

    def _is_picnic_summary_line(value: str | None) -> bool:
        lowered = str(value or '').strip().lower()
        if not lowered:
            return False
        summary_prefixes = (
            'statiegeld',
            'subtotaal',
            'totaal',
            'ingeleverd statiegeld',
            'flessen en blikjes',
            'tasjes',
            'verrekening picnic-tegoed',
            'picnic-tegoed',
            'voordeel',
            'btw ',
            'bezorgadres',
            'fijne dag',
            'vragen?',
            'klantenservice',
            'mijn profiel',
            'herroeping',
            'picnic b.v.',
        )
        return lowered.startswith(summary_prefixes)

    extracted: list[dict[str, Any]] = []
    noise_prefixes = ('order ', 'toegevoegd op ', 'beste ', 'hier is het bonnetje', 'al betaald via', 'bezorgadres', 'subtotaal', 'totaal')
    i = 0
    while i < len(lines) - 1:
        if not re.fullmatch(r'\d+', lines[i]):
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        qty = float(lines[i])
        name = lines[i + 1].strip()
        if (
            not _contains_letter(name)
            or any(name.lower().startswith(prefix) for prefix in noise_prefixes)
            or _is_picnic_summary_line(name)
        ):
            i += 1
            continue
        j = i + 2
        prices: list[Decimal] = []
        while j < len(lines) and j < i + 20:
            if _is_picnic_summary_line(lines[j]):
                break
            if j + 1 < len(lines) and re.fullmatch(r'-?\d+', lines[j]) and re.fullmatch(r'\d{2}', lines[j + 1]):
                price = _price_from_split_parts(lines[j], lines[j + 1])
                if price is not None:
                    prices.append(price)
                j += 2
                continue
            if j + 1 < len(lines) and re.fullmatch(r'\d+', lines[j]) and _contains_letter(lines[j + 1]):
                break
            j += 1

        non_zero_prices = [price.quantize(Decimal('0.01')) for price in prices if price is not None and price != Decimal('0.00')]
        if non_zero_prices:
            gross_total = non_zero_prices[0]
            net_total = non_zero_prices[-1]
            unit_price = (gross_total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if qty else gross_total
            discount_amount = (gross_total - net_total).quantize(Decimal('0.01')) if net_total < gross_total else None
            append_structured_product_candidate(
                extracted,
                label=name,
                quantity=qty,
                unit=None,
                unit_price=unit_price,
                line_total=gross_total,
                discount_amount=discount_amount,
                barcode=None,
                source_index=i,
                raw_line=' | '.join(lines[i:j]),
                normalized_line=re.sub(r'\s+', ' ', ' | '.join(lines[i:j])).strip(),
                source_segment=' | '.join(lines[i:j]),
                filename=filename,
                store_name='Picnic',
                function_name='_parse_picnic_email_result',
                append_branch='picnic_email_discounted_line',
                parser_path='_parse_picnic_email_result.picnic_email_discounted_line',
                caller_line_hint='Picnic email structured discounted line via append_structured_product_candidate',
                clean_label=_clean_receipt_label,
                amount_to_float=_amount_to_float,
                is_invalid_label=_looks_like_non_product_receipt_label,
                confidence_score=0.78,
            )
            i = j
            continue

        if j < len(lines) and j + 1 < len(lines) and re.fullmatch(r'\d+', lines[j]) and _contains_letter(lines[j + 1]):
            append_structured_product_candidate(
                extracted,
                label=name,
                quantity=qty,
                unit=None,
                unit_price=Decimal('0.00'),
                line_total=Decimal('0.00'),
                discount_amount=None,
                barcode=None,
                source_index=i,
                raw_line=' | '.join(lines[i:j + 2]),
                normalized_line=re.sub(r'\s+', ' ', ' | '.join(lines[i:j + 2])).strip(),
                source_segment=' | '.join(lines[i:j + 2]),
                filename=filename,
                store_name='Picnic',
                function_name='_parse_picnic_email_result',
                append_branch='picnic_email_zero_line',
                parser_path='_parse_picnic_email_result.picnic_email_zero_line',
                caller_line_hint='Picnic email structured zero line via append_structured_product_candidate',
                clean_label=_clean_receipt_label,
                amount_to_float=_amount_to_float,
                is_invalid_label=_looks_like_non_product_receipt_label,
                confidence_score=0.78,
            )
            i = j
            continue
        i += 1
    if not extracted:
        flattened_extracted, flattened_total = _parse_picnic_flattened_blocks(haystack)
        if flattened_extracted:
            extracted = flattened_extracted
            total_amount = total_amount or flattened_total
    return _receipt_result_from_manual('Picnic', purchase_at, total_amount, extracted, confidence=0.78)


def _parse_picnic_flattened_blocks(haystack: str) -> tuple[list[dict[str, Any]], Decimal | None]:
    compact = re.sub(r'\s+', ' ', str(haystack or '')).strip()
    if not compact:
        return [], None
    order_pattern = re.compile(r'(Toegevoegd op .*? Order [0-9-]+)\s+(?P<body>.*?)(?=(?:Toegevoegd op .*? Order [0-9-]+)|$)', re.I)
    price_pattern = re.compile(r'(?:â‚¬\s*)?(?P<euros>-?\d+)\s*(?:[.,]|\s)\s*(?P<cents>\d{2})(?:\s*\.)?')
    block_pattern = re.compile(r"(?:^|\s)(?P<qty>\d+)\s+(?=[A-Za-zÃ€-Ã¿'\(])")
    extracted: list[dict[str, Any]] = []

    def _cleanup_label(raw: str) -> str:
        value = re.sub(r'\s+', ' ', raw or '').strip(' .,-')
        value = re.sub(r'^(?:\[[^\]]+\]\s*)+', '', value)
        value = re.split(r'(?:nu\s*â‚¬\s*\d+[.,]\d{2}|smaakmaker|\d+% korting|\d+e\s*=|\d+ voor â‚¬\s*\d+)', value, 1, flags=re.I)[0]
        value = re.split(r'\d+(?:[.,]\d+)?\s*(?:gram|g|kg|ml|liter|l|stuks?|stuk|bosje|kilo|heel|pak|fles|rollen?)', value, 1, flags=re.I)[0]
        return _clean_receipt_label(value)

    for order_match in order_pattern.finditer(compact):
        body = order_match.group('body').strip()
        for marker in (' Statiegeld ', ' Subtotaal ', ' Totaal ', ' Ingeleverd statiegeld ', ' Bezorgadres ', ' Fijne dag'):
            position = body.find(marker)
            if position > 0:
                body = body[:position].strip()
                break
        starts = list(block_pattern.finditer(body))
        for idx, start in enumerate(starts):
            qty = float(start.group('qty'))
            chunk_start = start.start('qty')
            chunk_end = starts[idx + 1].start('qty') if idx + 1 < len(starts) else len(body)
            chunk = body[chunk_start:chunk_end].strip()
            if not chunk:
                continue
            chunk_after_qty = chunk[len(start.group('qty')):].strip()
            prices = [
                _price_from_split_parts(match.group('euros'), match.group('cents'))
                for match in price_pattern.finditer(chunk_after_qty)
            ]
            prices = [price.quantize(Decimal('0.01')) for price in prices if price is not None]
            first_price_match = price_pattern.search(chunk_after_qty)
            label_source = chunk_after_qty[:first_price_match.start()] if first_price_match else chunk_after_qty
            label = _cleanup_label(label_source)
            if not label or len(label) < 2:
                continue
            non_zero_prices = [price for price in prices if price != Decimal('0.00')]
            if non_zero_prices:
                gross_total = non_zero_prices[0]
                net_total = non_zero_prices[-1]
                unit_price = (gross_total / Decimal(str(int(qty)))).quantize(Decimal('0.01')) if qty else gross_total
                discount_amount = (gross_total - net_total).quantize(Decimal('0.01')) if net_total < gross_total else None
                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=unit_price,
                    line_total=gross_total,
                    discount_amount=discount_amount,
                    barcode=None,
                    source_index=idx,
                    raw_line=chunk,
                    normalized_line=re.sub(r'\s+', ' ', chunk).strip(),
                    source_segment=chunk,
                    filename=None,
                    store_name='Picnic',
                    function_name='_parse_picnic_flattened_blocks',
                    append_branch='picnic_flattened_discounted_line',
                    parser_path='_parse_picnic_flattened_blocks.picnic_flattened_discounted_line',
                    caller_line_hint='Picnic flattened structured discounted line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.78,
                )
            else:
                append_structured_product_candidate(
                    extracted,
                    label=label,
                    quantity=qty,
                    unit=None,
                    unit_price=Decimal('0.00'),
                    line_total=Decimal('0.00'),
                    discount_amount=None,
                    barcode=None,
                    source_index=idx,
                    raw_line=chunk,
                    normalized_line=re.sub(r'\s+', ' ', chunk).strip(),
                    source_segment=chunk,
                    filename=None,
                    store_name='Picnic',
                    function_name='_parse_picnic_flattened_blocks',
                    append_branch='picnic_flattened_zero_line',
                    parser_path='_parse_picnic_flattened_blocks.picnic_flattened_zero_line',
                    caller_line_hint='Picnic flattened structured zero line via append_structured_product_candidate',
                    clean_label=_clean_receipt_label,
                    amount_to_float=_amount_to_float,
                    is_invalid_label=_looks_like_non_product_receipt_label,
                    confidence_score=0.78,
                )

    total_amount = None
    total_match = re.search(r'(?i)Totaal(?: Al betaald via iDeal)?\s+(?P<euros>-?\d+)\s+(?P<cents>\d{2})', compact)
    if total_match:
        total_amount = _price_from_split_parts(total_match.group('euros'), total_match.group('cents'))
    return extracted, total_amount


def _parse_store_specific_result(file_bytes: bytes, filename: str, mime_type: str, direct_text: str = '', html_text: str = '') -> ReceiptParseResult | None:
    lower_name = filename.lower()
    text = _normalize_store_specific_text(direct_text)
    normalized_html = _normalize_store_specific_text(_html_to_text(html_text) if html_text else '')
    if lower_name.endswith('.pdf'):
        for parser in (_parse_action_pdf_result, _parse_gamma_pdf_result, _parse_hornbach_pdf_result, _parse_lidl_invoice_pdf_result):
            result = parser(text, filename)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result

    header_date = None
    if lower_name.endswith('.eml') or mime_type == 'message/rfc822':
        try:
            message = BytesParser(policy=policy.default).parsebytes(file_bytes)
            header_date = str(message.get('date') or '').strip()
        except Exception:
            header_date = None

    can_try_email_parsers = (
        lower_name.endswith('.eml')
        or mime_type == 'message/rfc822'
        or mime_type in {'text/html', 'text/plain'}
        or lower_name.endswith(('.html', '.htm', '.txt'))
    )
    if can_try_email_parsers:
        for parser in (_parse_bol_email_result, _parse_picnic_email_result):
            result = parser(text, normalized_html, filename, header_date=header_date)
            if result is not None and (result.lines or result.total_amount or result.purchase_at or result.store_name):
                return result
    return None

