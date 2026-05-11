from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)


def _has_pattern(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _has_ah_context(text: str, lines: list[str]) -> bool:
    """Return True only for strong Albert Heijn signals in receipt content.

    A loose token such as "AH" is not enough. OCR can easily create short tokens
    from noise. Albert Heijn detection therefore requires either the full name,
    an official AH URL/domain, or AH together with AH-specific receipt context.
    """
    if _has_pattern(r'\balbert\s*heijn\b', text):
        return True
    if _has_pattern(r'\bah\.nl\b|\bwww\.ah\.nl\b', text):
        return True

    ah_token_present = any(_has_pattern(r'\bah\b', line) for line in lines[:12])
    if not ah_token_present:
        return False

    ah_context_patterns = [
        r'\bbonus\b',
        r'\bbonuskaart\b',
        r'\bpersoonlijke\s+bonus\b',
        r'\bkoopzegels?\b',
        r'\ballerhande\b',
        r'\bah\s+(?:m|grf|hv|poffertje|chips|bouillon|tortilla|malbec)\b',
        r'\bt\s+ah\b',
    ]
    return any(_has_pattern(pattern, text) for pattern in ah_context_patterns)


def _store_from_text_content_only(lines: Iterable[str], filename: str) -> str | None:
    """Detect store chain from OCR/PDF/HTML receipt content only.

    Filename is intentionally ignored. Store classification must be based on
    receipt content and not on upload names, because filenames are external test
    artefacts and may be edited by users.
    """
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines]
    normalized_lines = [line for line in normalized_lines if line]
    haystack = ' '.join(normalized_lines).lower()

    if _has_ah_context(haystack, normalized_lines):
        return 'Albert Heijn'
    if _has_pattern(r'\bjumbo\b', haystack):
        return 'Jumbo'
    if _has_pattern(r'\blidl\b', haystack):
        return 'Lidl'
    if _has_pattern(r'\bplus\b', haystack):
        return 'Plus'
    if _has_pattern(r'\baldi\b', haystack):
        return 'ALDI'
    if _has_pattern(r'\baction\b', haystack):
        return 'Action'
    if _has_pattern(r'\bgamma\b', haystack):
        return 'Gamma'
    if _has_pattern(r'\bhornbach\b', haystack):
        return 'Hornbach'
    if _has_pattern(r'\bpicnic\b', haystack):
        return 'Picnic'
    if _has_pattern(r'\bbol(?:\.com)?\b', haystack):
        return 'Bol'
    if _has_pattern(r'\bcoolblue\b', haystack):
        return 'Coolblue'
    if _has_pattern(r'\bkarwei\b', haystack):
        return 'Karwei'
    if _has_pattern(r'\bmedia\s*markt\b|\bmediamarkt\b', haystack):
        return 'MediaMarkt'

    return None


def install_receipt_store_detection_patch(*_: Any) -> bool:
    _receipt_service._store_from_text = _store_from_text_content_only
    _receipt_service._rezzerv_store_detection_patch_installed = True
    LOGGER.info('Receipt store detection content-only patch installed')
    return True


install_receipt_store_detection_patch()
