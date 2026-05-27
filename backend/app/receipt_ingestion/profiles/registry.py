"""Receipt store profile registry.

R9-35A creates the registry boundary. Existing runtime detection remains in place
until the next migration steps move profiles behind this registry.
"""

from __future__ import annotations

from typing import Iterable

from app.receipt_ingestion.profiles.base import ReceiptStoreProfile


_REGISTERED_PROFILES: list[ReceiptStoreProfile] = []


def register_profile(profile: ReceiptStoreProfile) -> None:
    if profile not in _REGISTERED_PROFILES:
        _REGISTERED_PROFILES.append(profile)


def iter_profiles() -> Iterable[ReceiptStoreProfile]:
    return tuple(_REGISTERED_PROFILES)