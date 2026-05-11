from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from app.services import receipt_service as _receipt_service

LOGGER = logging.getLogger(__name__)
_ORIGINAL_STORE_FROM_TEXT = getattr(_receipt_service, '_store_from_text', None)


def _store_from_filename(filename: str) -> str | None:
    """Return a strong store hint from the uploaded filename.

    Photo OCR may hallucinate short supermarket tokens such as "AH". When the
    filename contains an explicit supermarket name, that filename signal should
    not be overridden by a loose OCR token.
    """
    normalized_filename = re.sub(r'[^a-z0-9]+', ' ', str(filename or '').lower()).strip()
    filename_tokens = set(normalized_filename.split())
    if not filename_tokens:
        return None

    compact_filename = re.sub(r'[^a-z0-9]+', '', str(filename or '').lower())
    filename_store_patterns: list[tuple[str, tuple[set[str], ...]]] = [
        ('Albert Heijn', ({'albert', 'heijn'}, {'ah'})),
        ('Jumbo', ({'jumbo'},)),
        ('Lidl', ({'lidl'},)),
        ('Plus', ({'plus'},)),
        ('ALDI', ({'aldi'},)),
        ('Action', ({'action'},)),
        ('Gamma', ({'gamma'},)),
        ('Hornbach', ({'hornbach'},)),
        ('Picnic', ({'picnic'},)),
        ('Bol', ({'bol'}, {'bolcom'})),
        ('Coolblue', ({'coolblue'},)),
        ('Karwei', ({'karwei'},)),
        ('MediaMarkt', ({'mediamarkt'}, {'media', 'markt'})),
    ]

    for store_name, token_sets in filename_store_patterns:
        for token_set in token_sets:
            if token_set.issubset(filename_tokens):
                return store_name
            if len(token_set) == 1 and next(iter(token_set)) in compact_filename:
                return store_name
    return None


def _store_from_text_with_filename_guard(lines: Iterable[str], filename: str) -> str | None:
    filename_store = _store_from_filename(filename)
    if filename_store:
        return filename_store
    if callable(_ORIGINAL_STORE_FROM_TEXT):
        return _ORIGINAL_STORE_FROM_TEXT(lines, filename)
    return None


def install_receipt_store_detection_patch(*_: Any) -> bool:
    if getattr(_receipt_service, '_rezzerv_store_detection_patch_installed', False):
        return False
    _receipt_service._store_from_filename = _store_from_filename
    _receipt_service._store_from_text = _store_from_text_with_filename_guard
    _receipt_service._rezzerv_store_detection_patch_installed = True
    LOGGER.info('Receipt store detection patch installed')
    return True


install_receipt_store_detection_patch()
