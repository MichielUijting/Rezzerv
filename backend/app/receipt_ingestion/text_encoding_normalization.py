"""
Generic text encoding normalization for receipt labels.

This module contains no product, brand or retailer knowledge. It only repairs
common mojibake sequences that occur when UTF-8 text has previously been read
as a legacy single-byte encoding.
"""

from __future__ import annotations

import re
from typing import Any

MOJIBAKE_MARKERS = ('\u00c3', '\u00c2', '\u00e2')

MOJIBAKE_REPLACEMENTS = {
    '\u00c3\u20ac': '\u00c0',
    '\u00c3\u0081': '\u00c1',
    '\u00c3\u201a': '\u00c2',
    '\u00c3\u0192': '\u00c3',
    '\u00c3\u201e': '\u00c4',
    '\u00c3\u2026': '\u00c5',
    '\u00c3\u2021': '\u00c7',
    '\u00c3\u02c6': '\u00c8',
    '\u00c3\u2030': '\u00c9',
    '\u00c3\u0160': '\u00ca',
    '\u00c3\u2039': '\u00cb',
    '\u00c3\u0152': '\u00cc',
    '\u00c3\u008d': '\u00cd',
    '\u00c3\u017d': '\u00ce',
    '\u00c3\u008f': '\u00cf',
    '\u00c3\u2018': '\u00d1',
    '\u00c3\u2019': '\u00d2',
    '\u00c3\u201c': '\u00d3',
    '\u00c3\u201d': '\u00d4',
    '\u00c3\u2022': '\u00d5',
    '\u00c3\u2013': '\u00d6',
    '\u00c3\u2122': '\u00d9',
    '\u00c3\u0161': '\u00da',
    '\u00c3\u203a': '\u00db',
    '\u00c3\u0153': '\u00dc',
    '\u00c3\u00a0': '\u00e0',
    '\u00c3\u00a1': '\u00e1',
    '\u00c3\u00a2': '\u00e2',
    '\u00c3\u00a3': '\u00e3',
    '\u00c3\u00a4': '\u00e4',
    '\u00c3\u00a5': '\u00e5',
    '\u00c3\u00a7': '\u00e7',
    '\u00c3\u00a8': '\u00e8',
    '\u00c3\u00a9': '\u00e9',
    '\u00c3\u00aa': '\u00ea',
    '\u00c3\u00ab': '\u00eb',
    '\u00c3\u00ac': '\u00ec',
    '\u00c3\u00ad': '\u00ed',
    '\u00c3\u00ae': '\u00ee',
    '\u00c3\u00af': '\u00ef',
    '\u00c3\u00b1': '\u00f1',
    '\u00c3\u00b2': '\u00f2',
    '\u00c3\u00b3': '\u00f3',
    '\u00c3\u00b4': '\u00f4',
    '\u00c3\u00b5': '\u00f5',
    '\u00c3\u00b6': '\u00f6',
    '\u00c3\u00b9': '\u00f9',
    '\u00c3\u00ba': '\u00fa',
    '\u00c3\u00bb': '\u00fb',
    '\u00c3\u00bc': '\u00fc',
    '\u00c3\u00bd': '\u00fd',
    '\u00c3\u00bf': '\u00ff',
    '\u00c2\u00ae': '\u00ae',
    '\u00c2\u00a9': '\u00a9',
    '\u00c2\u00b0': '\u00b0',
    '\u00c2\u00b1': '\u00b1',
    '\u00c2\u00b7': '\u00b7',
    '\u00e2\u201a\u00ac': '\u20ac',
    '\u00e2\u20ac\u201c': '\u2013',
    '\u00e2\u20ac\u201d': '\u2014',
    '\u00e2\u20ac\u02dc': '\u2018',
    '\u00e2\u20ac\u2122': '\u2019',
    '\u00e2\u20ac\u0153': '\u201c',
    '\u00e2\u20ac\u009d': '\u201d',
}


def _looks_like_mojibake(value: str) -> bool:
    return any(marker in value for marker in MOJIBAKE_MARKERS)


def _repair_latin1_utf8_mojibake(value: str) -> str | None:
    """Try generic repair for text decoded as latin1 while it was UTF-8."""
    if not _looks_like_mojibake(value):
        return None
    try:
        repaired = value.encode('latin1').decode('utf-8')
    except UnicodeError:
        return None
    return repaired if repaired != value else None


def _apply_explicit_replacements(value: str) -> tuple[str, list[str]]:
    normalized = value
    applied: list[str] = []
    for broken, repaired in MOJIBAKE_REPLACEMENTS.items():
        if broken in normalized:
            normalized = normalized.replace(broken, repaired)
            applied.append(broken)
    return normalized, applied


def normalize_receipt_text_encoding(value: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Repair common mojibake in receipt text without semantic corrections."""
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return None, None

    normalized = text
    applied: list[str] = []

    codec_repaired = _repair_latin1_utf8_mojibake(normalized)
    if codec_repaired:
        normalized = codec_repaired
        applied.append('latin1_utf8_mojibake_repair')

    normalized, explicit_applied = _apply_explicit_replacements(normalized)
    applied.extend(explicit_applied)

    normalized = re.sub(r'\s+', ' ', normalized).strip()
    if normalized == text:
        return normalized, None
    return normalized, {
        'original_text': text,
        'normalized_text': normalized,
        'encoding_replacements': applied,
    }
