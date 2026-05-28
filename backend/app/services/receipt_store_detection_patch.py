from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)


try:
    from . import receipt_debug_artifacts_patch  # noqa: F401
except Exception as exc:  # pragma: no cover - diagnostics must not break startup
    LOGGER.warning('receipt_debug_artifacts_patch_activation_failed error=%s', exc)


def _has_pattern(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _compact(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _first_lines(lines: list[str], count: int = 8) -> str:
    return ' '.join(lines[:count]).lower()


def _has_competing_strong_store(text: str, store: str) -> bool:
    strong_patterns = {
        'Albert Heijn': (r'\balbert\s*heijn\b', r'\bah\.nl\b', r'\bwww\.ah\.nl\b'),
        'Jumbo': (r'\bjumbo\b',),
        'Lidl': (r'\blidl\b',),
        'Plus': (r'\bplus\b',),
        'ALDI': (r'\baldi\b',),
    }
    for candidate, patterns in strong_patterns.items():
        if candidate == store:
            continue
        if any(_has_pattern(pattern, text) for pattern in patterns):
            return True
    return False


def _has_aldi_context(text: str, lines: list[str]) -> bool:
    """Detect ALDI from content only, including common OCR logo variants."""
    if _has_pattern(r'\baldi\b', text):
        return True
    if _has_competing_strong_store(text, 'ALDI'):
        return False

    header = _first_lines(lines, 8)
    header_compact_lines = [_compact(line) for line in lines[:8]]
    aldi_logo_variants = {'aldi', 'ald1', 'a1di', 'aldl', 'aidi'}
    if any(value in aldi_logo_variants for value in header_compact_lines):
        return True
    if any(re.search(r'\b(?:aldi|ald1|a1di|aldl|aidi)\b', line, flags=re.IGNORECASE) for line in lines[:8]):
        return True

    aldi_receipt_context = (
        r'\bbon\s*nr\b',
        r'\bfiliaal\b',
        r'\bkassier\b',
        r'\bwelkom\b',
    )
    has_logo_like = any(any(variant in compact for variant in aldi_logo_variants) for compact in header_compact_lines)
    has_receipt_context = any(_has_pattern(pattern, header) for pattern in aldi_receipt_context)
    return has_logo_like and has_receipt_context


def _has_ah_private_label_cluster(text: str, lines: list[str]) -> bool:
    """Detect AH from repeated AH private-label/product lines.

    Some scanned AH receipts have weak or missing header OCR. In that case the
    product block can still be decisive: multiple AH-prefixed private label
    products and/or KOOPZEGELS PREMIUM are strong Albert Heijn content signals.
    This remains filename-independent and is rejected when another chain is
    explicitly present.
    """
    if _has_competing_strong_store(text, 'Albert Heijn'):
        return False

    ah_product_patterns = (
        r'\bah\s+(?:m|grf|hv|poffertje|chips|bouillon|tortilla|malbec|muffins?|melk|rookv)\b',
        r'\bzaans\s+h\s+mayo\b',
        r'\bkoopzegels?\s+premium\b',
    )
    ah_signal_count = 0
    for line in lines:
        lowered = line.lower()
        if any(_has_pattern(pattern, lowered) for pattern in ah_product_patterns):
            ah_signal_count += 1
    if ah_signal_count >= 2:
        return True

    # KOOPZEGELS PREMIUM plus an AH article line is also decisive.
    has_koopzegels_premium = _has_pattern(r'\bkoopzegels?\s+premium\b', text)
    has_ah_article = any(_has_pattern(r'\bah\s+[a-z0-9]', line.lower()) for line in lines)
    return has_koopzegels_premium and has_ah_article


def _has_ah_context(text: str, lines: list[str]) -> bool:
    """Return True only for strong Albert Heijn signals in receipt content."""
    if _has_pattern(r'\balbert\s*heijn\b', text):
        return True
    if _has_pattern(r'\bah\.nl\b|\bwww\.ah\.nl\b', text):
        return True
    if _has_ah_private_label_cluster(text, lines):
        return True
    if _has_competing_strong_store(text, 'Albert Heijn'):
        return False

    ah_token_in_header = any(_has_pattern(r'\bah\b', line) for line in lines[:6])
    if not ah_token_in_header:
        return False

    header = _first_lines(lines, 10)
    ah_context_patterns = [
        r'\bbonus\b',
        r'\bbonuskaart\b',
        r'\bpersoonlijke\s+bonus\b',
        r'\bkoopzegels?\b',
        r'\ballerhande\b',
        r'\bah\s+(?:m|grf|hv|poffertje|chips|bouillon|tortilla|malbec)\b',
        r'\bt\s+ah\b',
        r'\bklantenservice\b',
        r'\bbon\s*nr\b',
        r'\btransactie\b',
        r'\bkassa\b',
    ]
    if any(_has_pattern(pattern, text) for pattern in ah_context_patterns):
        return True
    return _has_pattern(r'\bah\b', header)


def _store_from_text_content_only(lines: Iterable[str], filename: str) -> str | None:
    """Detect store chain from OCR/PDF/HTML receipt content only.

    Filename is intentionally ignored. Store classification must be based on
    receipt content and not on upload names, because filenames are external test
    artefacts and may be edited by users.
    """
    normalized_lines = [re.sub(r'\s+', ' ', str(line or '')).strip() for line in lines]
    normalized_lines = [line for line in normalized_lines if line]
    haystack = ' '.join(normalized_lines).lower()

    # Strong full-chain content first. This prevents short OCR tokens like "AH"
    # from overruling an explicit PLUS, Jumbo, Lidl or ALDI receipt.
    if _has_pattern(r'\balbert\s*heijn\b|\bah\.nl\b|\bwww\.ah\.nl\b', haystack):
        return 'Albert Heijn'
    if _has_pattern(r'\bjumbo\b', haystack):
        return 'Jumbo'
    if _has_pattern(r'\blidl\b', haystack):
        return 'Lidl'
    if _has_pattern(r'\bplus\b', haystack):
        return 'Plus'
    if _has_aldi_context(haystack, normalized_lines):
        return 'ALDI'

    # AH can also be proven by a cluster of AH private-label lines in the
    # product block, which is common when a scanned header/logo is OCR-poor.
    if _has_ah_context(haystack, normalized_lines):
        return 'Albert Heijn'

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
