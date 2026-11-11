"""Shared alias scope for store-specific Catalogus article identities.

Only well-established chain-name variants are collapsed. Store-specific
article numbers must never be compared across different actual retailers.
"""
from __future__ import annotations

from app.services.external_article_product_link_service import (
    normalize_external_link_retailer_code,
)

_RETAILER_ALIASES = {
    "ah": ("ah", "albert-heijn", "albert-heijn-digitaal", "albertheijn"),
    "lidl": ("lidl", "lidl-nederland", "lidl-nederland-gmbh"),
}


def canonical_catalog_retailer(value: str | None) -> str:
    normalized = normalize_external_link_retailer_code(value)
    for canonical, aliases in _RETAILER_ALIASES.items():
        if normalized in aliases:
            return canonical
    return normalized


def catalog_retailer_aliases(value: str | None) -> tuple[str, ...]:
    canonical = canonical_catalog_retailer(value)
    return _RETAILER_ALIASES.get(canonical, (canonical,) if canonical else ())
