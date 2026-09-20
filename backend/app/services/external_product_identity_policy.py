from __future__ import annotations

import re
from typing import Any


_PRIVATE_LABEL_ALIASES_BY_RETAILER = {
    "albert heijn": ("albert heijn", "ah"),
    "ah": ("albert heijn", "ah"),
    "jumbo": ("jumbo",),
    "plus": ("plus",),
}

_RETAILER_DISPLAY_NAMES = {
    "albert heijn": "Albert Heijn",
    "ah": "Albert Heijn",
    "jumbo": "Jumbo",
    "plus": "PLUS",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize(value: Any) -> str:
    normalized = _clean(value).lower().replace("-", " ").replace(".", " ")
    normalized = re.sub(
        r"[^a-z0-9áéíóúàèìòùäëïöüâêîôûçñ\s]+",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    return " ".join(normalized.split())


def _contains_phrase(value: Any, phrase: str) -> bool:
    normalized_value = _normalize(value)
    normalized_phrase = _normalize(phrase)
    if not normalized_value or not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {normalized_value} "


def _starts_with_phrase(value: Any, phrase: str) -> bool:
    normalized_value = _normalize(value)
    normalized_phrase = _normalize(phrase)
    if not normalized_value or not normalized_phrase:
        return False
    return (
        normalized_value == normalized_phrase
        or normalized_value.startswith(f"{normalized_phrase} ")
    )


def retailer_private_label_aliases(retailer_code: Any) -> tuple[str, ...]:
    retailer = _normalize(retailer_code)
    return _PRIVATE_LABEL_ALIASES_BY_RETAILER.get(retailer, ())


def leading_private_label_marker(
    *,
    retailer_code: Any,
    receipt_text: Any,
) -> str:
    aliases = retailer_private_label_aliases(retailer_code)
    for alias in sorted(aliases, key=len, reverse=True):
        if _starts_with_phrase(receipt_text, alias):
            return alias
    return ""


def external_product_identity_compatibility(
    *,
    retailer_code: Any,
    receipt_text: Any,
    candidate_brand: Any,
    candidate_name: Any = "",
) -> dict[str, Any]:
    """Bescherm expliciete huismerkidentiteit tegen een ander extern merk.

    Deze guard is bewust smal. Alleen wanneer de bontekst zelf begint met een
    ondubbelzinnige huismerkmarker van de winkelketen (bijvoorbeeld AH bij
    Albert Heijn), moet het externe product die merkidentiteit ook aantonen.
    Derdenmerken bij dezelfde winkel blijven toegestaan wanneer de bontekst
    geen huismerkmarker bevat.
    """

    aliases = retailer_private_label_aliases(retailer_code)
    marker = leading_private_label_marker(
        retailer_code=retailer_code,
        receipt_text=receipt_text,
    )
    if not aliases or not marker:
        return {
            "ok": True,
            "reason": "",
            "private_label_marker": "",
            "candidate_brand": _clean(candidate_brand),
        }

    brand = _clean(candidate_brand)
    name = _clean(candidate_name)

    if brand:
        brand_matches = any(_contains_phrase(brand, alias) for alias in aliases)
        if brand_matches:
            return {
                "ok": True,
                "reason": "",
                "private_label_marker": marker,
                "candidate_brand": brand,
            }
    elif any(_starts_with_phrase(name, alias) for alias in aliases):
        return {
            "ok": True,
            "reason": "",
            "private_label_marker": marker,
            "candidate_brand": "",
        }

    retailer = _normalize(retailer_code)
    display_name = _RETAILER_DISPLAY_NAMES.get(
        retailer,
        _clean(retailer_code) or "de winkelketen",
    )
    actual = brand or name or "onbekend"
    expected = " / ".join(dict.fromkeys(aliases))

    return {
        "ok": False,
        "reason": "private_label_brand_conflict",
        "private_label_marker": marker,
        "candidate_brand": brand,
        "message": (
            f"Bonartikel '{_clean(receipt_text)}' is herkenbaar als huismerk "
            f"van {display_name} ({marker.upper()}), maar het geselecteerde "
            f"externe product heeft merk/productidentiteit '{actual}'. "
            f"Kies een product met passende merkidentiteit ({expected})."
        ),
    }


def assert_external_product_identity_compatible(
    *,
    retailer_code: Any,
    receipt_text: Any,
    candidate_brand: Any,
    candidate_name: Any = "",
) -> dict[str, Any]:
    result = external_product_identity_compatibility(
        retailer_code=retailer_code,
        receipt_text=receipt_text,
        candidate_brand=candidate_brand,
        candidate_name=candidate_name,
    )
    if not result.get("ok"):
        raise ValueError(
            str(result.get("message") or "Productidentiteit komt niet overeen")
        )
    return result
