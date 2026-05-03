import re

from .base import BaseReceiptProfile
from .ah import AlbertHeijnReceiptProfile
from .jumbo import JumboReceiptProfile
from .lidl import LidlReceiptProfile
from .aldi import AldiReceiptProfile
from .plus import PlusReceiptProfile

_PROFILES = [
    AlbertHeijnReceiptProfile(),
    JumboReceiptProfile(),
    LidlReceiptProfile(),
    AldiReceiptProfile(),
    PlusReceiptProfile(),
]

_GENERIC_PROFILE = BaseReceiptProfile()


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def select_receipt_profile(store_name: str | None):
    normalized = _norm(store_name)
    if not normalized:
        return _GENERIC_PROFILE

    for profile in _PROFILES:
        for alias in profile.store_aliases:
            if _norm(alias) in normalized:
                return profile

    return _GENERIC_PROFILE
