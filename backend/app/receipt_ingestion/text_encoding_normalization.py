"""
Generic text encoding normalization for receipt labels.

This module contains no product, brand or retailer knowledge. It only repairs
common mojibake sequences that occur when UTF-8 text has previously been read
as a legacy single-byte encoding.
"""

from __future__ import annotations

import re
from typing import Any

MOJIBAKE_REPLACEMENTS = {
    'Ã€': 'À',
    'Ã�': 'Á',
    'Ã‚': 'Â',
    'Ãƒ': 'Ã',
    'Ã„': 'Ä',
    'Ã…': 'Å',
    'Ã‡': 'Ç',
    'Ãˆ': 'È',
    'Ã‰': 'É',
    'ÃŠ': 'Ê',
    'Ã‹': 'Ë',
    'ÃŒ': 'Ì',
    'Ã�': 'Í',
    'ÃŽ': 'Î',
    'Ã�': 'Ï',
    'Ã‘': 'Ñ',
    'Ã’': 'Ò',
    'Ã“': 'Ó',
    'Ã”': 'Ô',
    'Ã•': 'Õ',
    'Ã–': 'Ö',
    'Ã™': 'Ù',
    'Ãš': 'Ú',
    'Ã›': 'Û',
    'Ãœ': 'Ü',
    'Ã ': 'à',
    'Ã¡': 'á',
    'Ã¢': 'â',
    'Ã£': 'ã',
    'Ã¤': 'ä',
    'Ã¥': 'å',
    'Ã§': 'ç',
    'Ã¨': 'è',
    'Ã©': 'é',
    'Ãª': 'ê',
    'Ã«': 'ë',
    'Ã¬': 'ì',
    'Ã­': 'í',
    'Ã®': 'î',
    'Ã¯': 'ï',
    'Ã±': 'ñ',
    'Ã²': 'ò',
    'Ã³': 'ó',
    'Ã´': 'ô',
    'Ãµ': 'õ',
    'Ã¶': 'ö',
    'Ã¹': 'ù',
    'Ãº': 'ú',
    'Ã»': 'û',
    'Ã¼': 'ü',
    'Ã½': 'ý',
    'Ã¿': 'ÿ',
    'Â®': '®',
    'Â©': '©',
    'Â°': '°',
    'Â±': '±',
    'Â·': '·',
    'â‚¬': '€',
    'â€“': '–',
    'â€”': '—',
    'â€˜': '‘',
    'â€™': '’',
    'â€œ': '“',
    'â€': '”',
}


def normalize_receipt_text_encoding(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Repair common mojibake in receipt text without semantic corrections."""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return None, None
    normalized = text
    applied: list[str] = []
    for broken, repaired in MOJIBAKE_REPLACEMENTS.items():
        if broken in normalized:
            normalized = normalized.replace(broken, repaired)
            applied.append(broken)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if normalized == text:
        return normalized, None
    return normalized, {
        'original_text': text,
        'normalized_text': normalized,
        'encoding_replacements': applied,
    }
