"""Curated, read-only product-family and exact package-unit rules.

No synonym link, global identity, household article or stock may be written here.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import re
import unicodedata

# Only the fresh courgette variants explicitly illustrated in the PO design.
_BASE = {"courgette", "courgettes"}
_ALLOWED = _BASE | {"biologisch", "biologische", "bio", "groen", "groene", "geel", "gele"}
_RETAILER = {"ah", "jumbo", "lidl", "albert", "heijn"}
UNITS = {
    "g": ("mass", Decimal("1")), "kg": ("mass", Decimal("1000")),
    "ml": ("volume", Decimal("1")), "l": ("volume", Decimal("1000")),
    "stuk": ("count", Decimal("1")), "stuks": ("count", Decimal("1")),
}


def approved_family(product):
    """Return a family only if the full known product label passes its whitelist."""
    source = " ".join([str(product.get("name") or ""), str(product.get("variant") or "")])
    source = unicodedata.normalize("NFKD", source.lower())
    source = "".join(c for c in source if not unicodedata.combining(c))
    words = [w for w in re.findall(r"[a-z0-9]+", source) if w not in _RETAILER]
    if sum(word in _BASE for word in words) != 1 or not set(words) <= _ALLOWED:
        return None  # Frozen, soups, baby food, mixes and unknown additives fail closed.
    if set(words) & {"groen", "groene"} and set(words) & {"geel", "gele"}:
        return None
    return "verse_courgette_v1"


def shared_approved_family(left, right):
    family = approved_family(left)
    return family if family and family == approved_family(right) else None


def normalized_package_quantity(product):
    """Use explicit finite positive amount and only exact known SI/count units."""
    unit = str(product.get("size_unit") or "").strip().lower()
    if unit not in UNITS or isinstance(product.get("size_value"), bool):
        return None
    value = product.get("size_value")
    if value is None:
        return None
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount <= 0:
            return None
        normalized = amount * UNITS[unit][1]
        if not normalized.is_finite():
            return None
    except (InvalidOperation, OverflowError, ValueError):
        return None
    return UNITS[unit][0], normalized


def verified_package_ratio(left, right):
    """Exact packages of RIGHT equivalent to one package of LEFT (read-only).

    No mass/volume/count crossover, guessed piece weights or unbounded ratio.
    """
    if not shared_approved_family(left, right):
        return None
    a, b = normalized_package_quantity(left), normalized_package_quantity(right)
    if not a or not b or a[0] != b[0]:
        return None
    ratio = Fraction(a[1]) / Fraction(b[1])
    if not Fraction(1, 1000) <= ratio <= Fraction(1000):
        return None
    return {
        "family": "verse_courgette_v1",
        "dimension": a[0],
        "left_to_right": str(ratio.numerator) if ratio.denominator == 1
                         else f"{ratio.numerator}/{ratio.denominator}",
        "rule": "exact_catalog_package_units_v1",
    }
