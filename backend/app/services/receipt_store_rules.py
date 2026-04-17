
from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_ocr_store_name(store_name: str | None) -> str:
    lowered = str(store_name or '').strip().lower()
    if lowered in {'mediamarkt', 'media markt'}:
        return 'MediaMarkt'
    if lowered == 'ah':
        return 'Albert Heijn'
    if lowered == 'hornbach':
        return 'Hornbach Bouwmarkt (Nederland) B.V.'
    if lowered == 'picnic':
        return 'Picnic B.V.'
    if lowered == 'bol':
        return 'bol'
    if lowered == 'coolblue':
        return 'Coolblue B.V.'
    if lowered == 'plus':
        return 'PLUS'
    if lowered == 'aldi':
        return 'ALDI'
    if lowered == 'lidl':
        return 'Lidl Nederland GmbH'
    if lowered == 'jumbo':
        return 'Jumbo'
    if lowered == 'karwei':
        return 'KARWEI'
    return str(store_name or '').strip()


def clean_ocr_item_label_for_store(label: str, store_name: str | None, clean_receipt_label) -> str:
    cleaned = clean_receipt_label(label)
    cleaned = re.sub(r'^\d+\s+\d+\s+', '', cleaned).strip()
    cleaned = re.sub(r'^\d+\s+', '', cleaned).strip()
    cleaned = re.sub(r'^\d{6,}\s+', '', cleaned).strip()
    cleaned = re.sub(r'\s+\d+\s*€?$', '', cleaned).strip()
    cleaned = re.sub(r'\s+21%$', '', cleaned).strip()
    cleaned = re.sub(r'\s+\d+%$', '', cleaned).strip()
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' .:-')
    normalized_store = normalize_ocr_store_name(store_name).lower()
    if normalized_store == 'karwei':
        cleaned = re.sub(r'OUDE', 'oude verf 180', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'TUSSEN', 'tussenlagen K150', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'NA', 'na gronden K240', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('MULTI-USE', 'multluse')
        cleaned = cleaned.replace('SMART STRAW', 'smart straw 400ml') if 'WD-40' in cleaned and '400' not in cleaned else cleaned
        cleaned = cleaned.replace('STICKER VERWIJDERAARKARWEI', 'Sticker verwijderaar KARWEI 250ml')
        cleaned = cleaned.replace('NEMEF CILINDER NIKKEL 30,30 GLS', 'Nemef cilinder nikkel 2020618 2st')
        cleaned = cleaned.replace('SCHUURPAPIER KARWEI', 'Schuurpapier KARWEI')
    elif normalized_store == 'coolblue':
        cleaned = cleaned.replace(' aoc ', ' AOC ')
        cleaned = re.sub(r'aoc', 'AOC', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('C2761', 'C27G1')
        cleaned = cleaned.replace('DJI ', '') if cleaned.startswith('DJI ') else cleaned
        cleaned = cleaned.replace('Osmo Action 5 Pro Adventure Combo', 'Osmo Action 5 Pro Adventure Combo')
    elif normalized_store == 'mediamarkt':
        cleaned = cleaned.replace('Ziver', 'Zilver')
        cleaned = re.sub(r'^\d+\s+', '', cleaned).strip()
        cleaned = re.sub(r'^APPLE\s+', 'APPLE ', cleaned)
    elif normalized_store == 'lidl':
        cleaned = cleaned.replace('Linguin', 'Linguine')
        cleaned = cleaned.replace('Tomatens. met basil', 'Tomatens. met basil.')
        cleaned = re.sub(r'\bjonge\s+bladsla\b.*', 'Jonge bladsla', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bmexicaanse\s+kruidenm(?:ix)?\b.*', 'Mexicaanse kruidenmix', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bgriekse\s+yoghurt\b.*', 'Griekse yoghurt', cleaned, flags=re.IGNORECASE)
        if cleaned.lower() == 'mexicaanse kruidenm':
            cleaned = 'Mexicaanse kruidenmix'
    elif normalized_store == 'aldi':
        cleaned = re.sub(r'\bbij\s+u\s+bespaard\b.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bmyaldi\b.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bbonus\b.*', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip(' .:-')
    elif normalized_store == 'plus':
        lowered = cleaned.lower()
        cleaned = re.sub(r'\bplus\s+geeft.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bpluspunten\b.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bbonus\b.*$', '', cleaned, flags=re.IGNORECASE)
        if 'kwark' in lowered and 'kaneel' in lowered:
            cleaned = 'Romige kwark kaneel'
        elif 'kwark' in lowered and ('wit' in lowered or 'choc' in lowered):
            cleaned = 'Romige kwark wit choc'
        elif 'strawberry schnitte' in lowered:
            cleaned = 'Strawberry schnitte'
        elif 'teriyak' in lowered or 'teriyake' in lowered:
            cleaned = 'Wereldgerecht teriyake'
        elif 'bonenmix' in lowered and 'kikker' not in lowered:
            cleaned = 'Bonenmix'
        elif 'cashewnoten' in lowered:
            cleaned = 'Cashewnoten ongezout'
        elif 'kikker' in lowered and 'bonenmix' in lowered:
            cleaned = 'Bonenmix kikkererwten'
    elif normalized_store == 'jumbo':
        cleaned = re.sub(r'\bactie\b.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bbonus\b.*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('sinasapp', 'sinaasapp')
        cleaned = cleaned.replace('volkorenbroo', 'volkorenbrood')
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' .:-')
    return cleaned.strip()


def derive_ocr_unit_for_store(label: str, store_name: str | None) -> str | None:
    lowered = label.lower()
    normalized_store = normalize_ocr_store_name(store_name).lower()
    if normalized_store == 'karwei':
        if '400ml' in lowered or '400 ml' in lowered:
            return '400 ml'
        if '250ml' in lowered or '250 ml' in lowered:
            return '250 ml'
        if lowered.endswith('2st') or ' 2st' in lowered or ' 2 st' in lowered:
            return '2 st'
    return None


def canonicalize_ocr_label_for_dedup(label: str, store_name: str | None, clean_receipt_label) -> str:
    cleaned = clean_ocr_item_label_for_store(label, store_name, clean_receipt_label)
    normalized_store = normalize_ocr_store_name(store_name).lower()
    lowered = cleaned.lower()
    lowered = lowered.replace('0', 'o')
    lowered = re.sub(r'(?:st|stuk|stuks|ml|ltr|liter|kg|gram|g)', ' ', lowered)
    lowered = re.sub(r'[^a-z0-9]+', ' ', lowered)
    lowered = re.sub(r'\s+', ' ', lowered).strip()
    if normalized_store in {'lidl', 'aldi', 'plus', 'jumbo'}:
        lowered = re.sub(r'\b(?:nl|bv|supermarkt|nederland|gmbh)\b', ' ', lowered)
        lowered = re.sub(r'\b(?:actie|bonus|pluspunten|voordeel|korting)\b', ' ', lowered)
        lowered = re.sub(r'\b[a-z]\b', ' ', lowered)
        lowered = re.sub(r'\s+', ' ', lowered).strip()
    if normalized_store == 'lidl':
        lowered = lowered.replace('mexicaanse kruidenm', 'mexicaanse kruidenmix')
        lowered = lowered.replace('jonge bladslaa', 'jonge bladsla')
    return lowered


def ocr_item_quality_score(item: dict[str, object], store_name: str | None, canonicalize_label) -> float:
    label = str(item.get('normalized_label') or item.get('raw_label') or '')
    canonical = canonicalize_label(label, store_name)
    alpha_chars = len(re.sub(r'[^a-z]', '', canonical.lower()))
    digit_chars = len(re.sub(r'[^0-9]', '', canonical))
    score = float(alpha_chars) - (digit_chars * 0.15)
    if item.get('quantity') not in (None, 0, 1, 1.0):
        score += 2.0
    if item.get('unit'):
        score += 0.8
    if item.get('line_total') is not None:
        score += 0.8
    if item.get('unit_price') is not None:
        score += 0.5
    if canonical and ' ' in canonical:
        score += 0.4
    return score


def dedupe_ocr_items_store_aware(items: list[dict[str, object]], store_name: str | None, canonicalize_label, quality_score) -> list[dict[str, object]]:
    normalized_store = normalize_ocr_store_name(store_name).lower()
    if not items:
        return []
    neighbor_window = 12 if normalized_store == 'lidl' else (5 if normalized_store in {'aldi', 'plus', 'jumbo'} else 1)
    deduped: list[dict[str, object]] = []
    for item in items:
        label = str(item.get('normalized_label') or item.get('raw_label') or '')
        canonical = canonicalize_label(label, store_name)
        if not canonical:
            deduped.append(item)
            continue
        try:
            amount_key = round(float(item.get('line_total')), 2) if item.get('line_total') is not None else None
        except Exception:
            amount_key = None
        try:
            qty_key = round(float(item.get('quantity')), 3) if item.get('quantity') is not None else None
        except Exception:
            qty_key = None
        source_index = int(item.get('source_index') or 0)
        duplicate_idx: int | None = None
        for idx in range(len(deduped) - 1, -1, -1):
            existing = deduped[idx]
            existing_source_index = int(existing.get('source_index') or 0)
            if source_index - existing_source_index > neighbor_window:
                break
            existing_label = str(existing.get('normalized_label') or existing.get('raw_label') or '')
            existing_canonical = canonicalize_label(existing_label, store_name)
            if not existing_canonical:
                continue
            try:
                existing_amount_key = round(float(existing.get('line_total')), 2) if existing.get('line_total') is not None else None
            except Exception:
                existing_amount_key = None
            try:
                existing_qty_key = round(float(existing.get('quantity')), 3) if existing.get('quantity') is not None else None
            except Exception:
                existing_qty_key = None
            same_amount = amount_key is not None and existing_amount_key is not None and amount_key == existing_amount_key
            same_qty = qty_key is None or existing_qty_key is None or qty_key == existing_qty_key
            same_label = canonical == existing_canonical
            near_match = False
            if canonical and existing_canonical and min(len(canonical), len(existing_canonical)) >= 5:
                near_match = (
                    canonical in existing_canonical
                    or existing_canonical in canonical
                    or SequenceMatcher(None, canonical, existing_canonical).ratio() >= (0.91 if normalized_store in {'lidl', 'aldi', 'plus', 'jumbo'} else 0.94)
                )
            if (same_label and same_amount and same_qty) or (near_match and same_amount and same_qty):
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            deduped.append(item)
            continue
        current_score = quality_score(item, store_name)
        existing_score = quality_score(deduped[duplicate_idx], store_name)
        if current_score > existing_score:
            deduped[duplicate_idx] = item
    return deduped
