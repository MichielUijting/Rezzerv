from .base import GenericProfile, ReceiptProfile
from .lidl import LidlProfile
from .jumbo import JumboProfile
from .aldi import AldiProfile


def get_profile_for_store(store_hint: str) -> ReceiptProfile:
    normalized = (store_hint or "unknown").strip().lower()
    if normalized == "lidl":
        return LidlProfile()
    if normalized == "jumbo":
        return JumboProfile()
    if normalized == "aldi":
        return AldiProfile()
    return GenericProfile()


__all__ = [
    "ReceiptProfile",
    "GenericProfile",
    "LidlProfile",
    "JumboProfile",
    "AldiProfile",
    "get_profile_for_store",
]
