"""Read-only, explainable product-equivalence review for Catalogus synonyms.

A review hint is never permission to create, remove or propagate a relation.
Keep product identity, existing classification conflicts and confirmation separate.
"""
from __future__ import annotations

import re
import unicodedata
from app.services.synonym_product_family_rules import (
    normalized_package_quantity, shared_approved_family, verified_package_ratio,
    proven_fresh_prepared_contrast,
)


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


def _catalog_name(value):
    # Product equivalence is independent of the retail channel. Only remove
    # explicitly known retailer tokens; keep all product/dietary adjectives.
    words = _plain(value).split()
    return " ".join(word for word in words
                    if word not in {"ah", "jumbo", "lidl", "albert", "heijn"})


def _contains(value, phrase):
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(_plain(phrase)) + r"(?![a-z0-9])", value))


def _specificity(value, choices):
    found = []
    for i, names in enumerate(choices):
        if any(_contains(value, name) for name in names):
            found.append(i)
    return set(found)


def _quantity(p):
    return normalized_package_quantity(p)


def proven_semantic_conflicts(left, right):
    """Only explicit incompatible product traits; unknown values do not prove equality."""
    name_l, name_r = _catalog_name(left.get("name")), _catalog_name(right.get("name"))
    text_l = _plain(" ".join((name_l, str(left.get("variant") or ""))))
    text_r = _plain(" ".join((name_r, str(right.get("variant") or ""))))
    warnings = []
    for label, alternatives in CONTRASTS:
        a, b = _specificity(text_l, alternatives), _specificity(text_r, alternatives)
        if len(a) == 1 and len(b) == 1 and a != b:
            warnings.append("Verschil in " + label)
    for a, b in (("mayonaise", "melk"), ("mayo", "melk"),
                 ("kwark", "yoghurt"), ("kwark", "yogurt"),
                 ("noten", "kruidnoten")):
        if (_contains(text_l, a) and _contains(text_r, b)
                or _contains(text_r, a) and _contains(text_l, b)):
            warnings.append("Verschillende productsoorten")
            break
    if proven_fresh_prepared_contrast(left, right):
        warnings.append("Verse courgette is geen bereid, diepvries- of babyproduct")
    return list(dict.fromkeys(warnings))


def review_pair(left, right):
    """Return conservative display-only signals, never an automatic link decision."""
    name_l, name_r = _catalog_name(left.get("name")), _catalog_name(right.get("name"))
    warnings = proven_semantic_conflicts(left, right)
    qa, qb = _quantity(left), _quantity(right)
    if qa and qb and qa[0] != qb[0]:
        warnings.append("Inhoudseenheid verschilt")
    elif qa and qb and qa[1] != qb[1]:
        warnings.append("Verpakkingsinhoud verschilt")
        ratio = verified_package_ratio(left, right)
        if ratio:
            warnings.append(
                f"Exacte verpakkingseenheden: 1 linker verpakking = "
                f"{ratio['left_to_right']} rechter verpakking; geen automatische voorraadafboeking"
            )
    if warnings:
        return {"review_level": "check", "review_label": "Controleren",
                "review_reason": "; ".join(dict.fromkeys(warnings))}
    # Curated families only improve a suggestion. Actual linking remains
    # the existing explicit, independently authorized server transaction.
    if qa and qb and qa == qb and shared_approved_family(left, right):
        return {"review_level": "strong", "review_label": "Sterke kandidaat",
                "review_reason": "Verse courgettefamilie en bekende gelijke inhoud; "
                                 "controleer het gebruiksdoel voor handmatige bevestiging."}
    if name_l and name_l == name_r and qa and qb and qa == qb:
        return {"review_level": "strong", "review_label": "Sterke kandidaat",
                "review_reason": "Zelfde artikelnaam en inhoud; controleer de overige productkenmerken."}
    return {"review_level": "possible", "review_label": "Beoordelen",
            "review_reason": "Controleer productsoort, variant, bereiding en inhoud."}
