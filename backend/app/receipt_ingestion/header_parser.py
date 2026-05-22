from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from app.receipt_ingestion.amounts import parse_decimal as _parse_decimal
from app.receipt_ingestion.fingerprints import (
    _is_plausible_purchase_at,
    _is_plausible_total_amount,
)

KNOWN_STORES = [
    'Albert Heijn', 'AH', 'Jumbo', 'Lidl', 'Plus', 'ALDI', 'Aldi', 'Action',
    'Gamma', 'Hornbach', 'Picnic', 'Bol', 'bol.com', 'Coolblue', 'Karwei',
    'MediaMarkt',
]


def _store_from_text(lines: Iterable[str], filename: str) -> str | None:
    haystack = ' '.join(lines).lower()
    compact_haystack = re.sub(r'[^a-z0-9]+', '', haystack)
    lower_filename = filename.lower()
    compact_filename = re.sub(r'[^a-z0-9]+', '', lower_filename)
    priority_patterns = [
        ('Albert Heijn', [r'\balbert\s*heijn\b', r'\bah\b']),
        ('Jumbo', [r'\bjumbo\b']),
        ('Lidl', [r'\blidl\b']),
        ('Plus', [r'\bplus\b']),
        ('ALDI', [r'\baldi\b']),
        ('Action', [r'\baction\b']),
        ('Gamma', [r'\bgamma\b']),
        ('Hornbach', [r'\bhornbach\b']),
        ('Picnic', [r'\bpicnic\b']),
        ('Bol', [r'\bbol(?:\.com)?\b']),
        ('Coolblue', [r'\bcoolblue\b']),
        ('Karwei', [r'\bkarwei\b']),
        ('MediaMarkt', [r'\bmedia\s*markt\b', r'\bmediamarkt\b']),
    ]
    for normalized_store, patterns in priority_patterns:
        for pattern in patterns:
            if re.search(pattern, haystack, flags=re.IGNORECASE) or re.search(pattern, lower_filename, flags=re.IGNORECASE):
                return normalized_store
    for store in KNOWN_STORES:
        normalized_store = 'Albert Heijn' if store == 'AH' else store.title() if store.islower() else store
        compact_store = re.sub(r'[^a-z0-9]+', '', store.lower())
        if compact_store and (compact_store in compact_haystack or compact_store in compact_filename):
            return normalized_store
    return None


def _looks_like_store_branch_line(value: str) -> bool:
    candidate = re.sub(r'\s+', ' ', str(value or '')).strip()
    lowered = candidate.lower()
    if not candidate or len(candidate) < 4:
        return False
    if any(token in lowered for token in ('www.', 'http', '@', 'openingstijden', 'telefoon', 'klantenservice', 'privacy', 'omschrijving', 'bedrag', 'supermarkten')):
        return False
    if re.fullmatch(r'\d{6,}', candidate):
        return False
    has_postcode = bool(re.search(r'\b\d{4}\s?[A-Z]{2}\b', candidate))
    has_address_number = bool(re.search(r'\b\d{1,4}[A-Za-z]?\b', candidate)) and bool(re.search(r'[A-Za-z]', candidate))
    return has_postcode or has_address_number


def _store_branch_from_lines(lines: Iterable[str], store_name: str | None) -> str | None:
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines]
    normalized_lines = [line for line in normalized_lines if line]
    if not normalized_lines:
        return None
    store_tokens = []
    if store_name:
        store_tokens.append(store_name.lower())
    if store_name and store_name.lower() == 'albert heijn':
        store_tokens.append('ah')
    explicit_store_index: int | None = None
    for index, line in enumerate(normalized_lines[:12]):
        lowered = line.lower()
        if 'www.' in lowered or '.com' in lowered:
            continue
        if any(token and token in lowered for token in store_tokens):
            explicit_store_index = index
            break

    def dedupe_candidates(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            cleaned = re.sub(r'^[^A-Za-z0-9]+', '', str(value or '')).strip()
            cleaned = re.sub(r'[^A-Za-z0-9]+$', '', cleaned).strip()
            if not cleaned:
                continue
            if cleaned.lower() in {item.lower() for item in result}:
                continue
            result.append(cleaned)
        return result

    if explicit_store_index is not None:
        candidates: list[str] = []
        for line in normalized_lines[explicit_store_index + 1: explicit_store_index + 6]:
            if not _looks_like_store_branch_line(line):
                if candidates:
                    break
                continue
            candidates.append(line)
            if len(candidates) >= 2:
                break
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]
    postcode_re = re.compile(r'\b\d{4}\s?[A-Z]{2}\b')
    address_re = re.compile(r'\b\d{1,4}[A-Za-z]?\b')
    for index, line in enumerate(normalized_lines[:8]):
        if not postcode_re.search(line):
            continue
        candidates = []
        if index > 0 and _looks_like_store_branch_line(normalized_lines[index - 1]) and address_re.search(normalized_lines[index - 1]):
            candidates.append(normalized_lines[index - 1])
        candidates.append(line)
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]
    for index, line in enumerate(normalized_lines[:8]):
        if not (_looks_like_store_branch_line(line) and address_re.search(line)):
            continue
        candidates = [line]
        if index + 1 < len(normalized_lines) and postcode_re.search(normalized_lines[index + 1]):
            candidates.append(normalized_lines[index + 1])
        candidates = dedupe_candidates(candidates)
        if candidates:
            return ', '.join(candidates[:2])[:255]
    return None


def _purchase_at_from_lines(lines: Iterable[str], filename: str) -> str | None:
    patterns = [
        re.compile(r'(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?))?'),
        re.compile(r'(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s+(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{4})'),
        re.compile(r'(?P<date>\d{4}-\d{2}-\d{2})(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?))?'),
    ]
    candidates: list[tuple[int, str]] = []
    for candidate in list(lines):
        normalized_candidate = str(candidate or '').strip()
        lowered = normalized_candidate.lower()
        for pattern in patterns:
            match = pattern.search(normalized_candidate)
            if not match:
                continue
            date_part = match.groupdict().get('date')
            time_part = match.groupdict().get('time') or '00:00:00'
            if not date_part:
                continue
            if len(time_part) == 5:
                time_part += ':00'
            for fmt in ('%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d'):
                try:
                    parsed = datetime.strptime(date_part, fmt)
                    hh, mm, ss = time_part.split(':')
                    parsed = parsed.replace(hour=int(hh), minute=int(mm), second=int(ss))
                    iso_value = parsed.isoformat()
                    if not _is_plausible_purchase_at(iso_value):
                        continue
                    score = 0
                    if 'betaling' in lowered:
                        score += 20
                    if match.groupdict().get('time'):
                        score += 10
                    if 'totaal' in lowered or 'auth.' in lowered:
                        score += 5
                    candidates.append((score, iso_value))
                except ValueError:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _total_amount_from_lines(lines: list[str], filename: str) -> tuple[Decimal | None, bool]:
    amount_pattern = re.compile(r'(-?\d{1,6}(?:[\.,]\d{2}))')
    explicit_total_pattern = re.compile(r'(?i)\b(totaal|te betalen|te voldoen|eindtotaal|total due|amount due)\b')
    subtotal_pattern = re.compile(r'(?i)\b(subtotaal|subtotal)\b')
    payment_pattern = re.compile(r'(?i)\b(bankpas|pinnen|pin|betaald|betaling)\b')
    vat_pattern = re.compile(r'(?i)\b(btw|bedr\.excl|bedr\.incl|bedrag excl|bedrag incl)\b')
    refund_pattern = re.compile(r'(?i)\b(retour|refund|credit)\b')
    candidates: list[tuple[int, int, Decimal, bool]] = []
    in_vat_block = False
    for index, line in enumerate(lines):
        lowered = str(line or '').lower()
        if vat_pattern.search(lowered) or lowered.startswith('%'):
            in_vat_block = True
        matches = amount_pattern.findall(str(line or ''))
        parsed_matches = [_parse_decimal(item) for item in matches]
        parsed_matches = [item for item in parsed_matches if item is not None]
        if not parsed_matches:
            continue
        if subtotal_pattern.search(lowered):
            continue
        if any(token in lowered for token in ('voordeel', 'korting', 'waarvan', 'bonus box')):
            continue
        explicit = bool(explicit_total_pattern.search(lowered))
        payment = bool(payment_pattern.search(lowered))
        if not explicit and not payment:
            continue
        amount = parsed_matches[-1]
        score = 0
        if explicit:
            score += 40
        if payment:
            score += 25
        if 'eur' in lowered:
            score += 10
        if in_vat_block or vat_pattern.search(lowered):
            score -= 100
        if refund_pattern.search(lowered):
            score -= 60
        if len(parsed_matches) > 1:
            score -= 10 * (len(parsed_matches) - 1)
        if _is_plausible_total_amount(amount):
            candidates.append((score, index, amount, explicit))
    if not candidates:
        return None, False
    valid_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    chosen = sorted(valid_candidates or candidates, key=lambda item: (item[0], item[1]))[-1]
    return chosen[2], chosen[3]
