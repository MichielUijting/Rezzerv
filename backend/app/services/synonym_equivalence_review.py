"""Read-only, explainable product-equivalence review for Catalogus synonyms.

A review hint is never permission to create, remove or propagate a relation.
Keep product identity, existing classification conflicts and confirmation separate.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


CONTRASTS = (
    ("melkvet", (("halfvolle", "halfvol"), ("volle", "vol"), ("magere", "mager"))),
    ("lactose", (("lactosevrij", "lactosevrije", "zonder lactose"), ("met lactose",))),
    ("zout", (("ongezouten", "zonder zout", "zoutloos"), ("gezouten",))),
    ("suiker", (("suikervrij", "suikervrije", "zonder suiker", "0% suiker"), ("met suiker",))),
    ("bereiding", (("gerookt", "gerookte"), ("ongerookt",))),
    ("smaak", (("naturel", "natuur"), ("vanille",), ("aardbei",), ("chocolade",), ("framboos",))),
    ("soort", (("kipgehakt",), ("rundergehakt", "rundgehakt"), ("gemengd gehakt",))),
)


def _plain(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _contains(value, phrase):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(_plain(phrase)) + r"(?![a-z0-9])", value))


def _specificity(value, choices):
    found = []
    for i, names in enumerate(choices):
        if any(_contains(value, name) for name in names):
            found.append(i)
    return set(found)


def _quantity(p):
    try:
        amount = Decimal(str(p.get("size_value") or ""))
    except InvalidOperation:
        return None
    unit = _plain(p.get("size_unit"))
    factors = {"kg": ("mass", 1000), "g": ("mass", 1),
               "l": ("volume", 1000), "ml": ("volume", 1),
               "stuk": ("count", 1), "stuks": ("count", 1)}
    if amount <= 0 or unit not in factors:
        return None
    dimension, factor = factors[unit]
    return dimension, amount * factor


def review_pair(left, right):
    """Return conservative display-only signals, never an automatic link decision."""
    name_l, name_r = _plain(left.get("name")), _plain(right.get("name"))
    # Include known variants, but do not interpret brand/store as a product property.
    text_l = _plain(" ".join((name_l, str(left.get("variant") or ""))))
    text_r = _plain(" ".join((name_r, str(right.get("variant") or ""))))
    warnings = []
    for label, alternatives in CONTRASTS:
        a, b = _specificity(text_l, alternatives), _specificity(text_r, alternatives)
        # Multiple alternatives in one item are ambiguous, not a proved contradiction.
        if len(a) == 1 and len(b) == 1 and a != b:
            warnings.append("Verschil in " + label)
    # Only flag an actual incompatible food type, not shared fragments ('noten'/'kruidnoten').
    category_words = (
        ("mayonaise", "mayo"), ("melk",), ("yoghurt", "yogurt"),
        ("kwark",), ("kruidnoten",), ("noten",), ("gehakt",),
    )
    for group in (("mayonaise", "melk"), ("kwark", "yoghurt"), ("noten", "kruidnoten")):
        if any(_contains(text_l, a) and _contains(text_r, b)
               or _contains(text_r, a) and _contains(text_l, b) for a in (group[0],) for b in (group[1],)):
            warnings.append("Verschillende productsoorten")
            break
    qa, qb = _quantity(left), _quantity(right)
    if qa and qb and qa[0] != qb[0]:
        warnings.append("Inhoudseenheid verschilt")
    elif qa and qb and qa[1] != qb[1]:
        warnings.append("Verpakkingsinhoud verschilt")
    if warnings:
        return {"review_level": "check", "review_label": "Controleren",
                "review_reason": "; ".join(dict.fromkeys(warnings))}
    # A textual match without verified distinct product attributes is only a candidate.
    if name_l and name_l == name_r and qa and qb and qa == qb:
        return {"review_level": "strong", "review_label": "Sterke kandidaat",
                "review_reason": "Zelfde artikelnaam en inhoud; controleer de overige productkenmerken."}
    return {"review_level": "possible", "review_label": "Beoordelen",
            "review_reason": "Controleer productsoort, variant, bereiding en inhoud."}
