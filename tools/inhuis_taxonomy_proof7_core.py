"""Conservatieve bredere Shopify-voorstellen uitsluitend NA een exacte OFF-GTIN-match.

Deze module gebruikt geen netwerk of database; zij produceert alleen voorstellen.
De bestaande uitkomst van proef 6 is leidend wanneer die een kandidaat of
ambiguïteit oplevert. Vooral op basis van namen wordt nooit automatisch opgeslagen.
"""

from collections import defaultdict
import re

from tools.inhuis_taxonomy_proof5_core import safe
from tools.inhuis_taxonomy_proof6_core import (
    _cbs_comparison, _is_parent, _norm, classify_off_product,
)


# Bewust korte, toetsbare vertaalsleutel naar ECHTE Shopify v2026-08-codes.
# Niet matchen op een willekeurige substring uit een barcode of winkelnaam.
OFF_CATEGORY_ALIASES = {
    "bouillon pots": "fb-2-18", "bouillon": "fb-2-18",
    "broth": "fb-2-18", "broths": "fb-2-18",
    "breakfast cereals": "fb-2-11-4", "ontbijtgranen": "fb-2-11-4",
    "cured sausages": "fb-2-12-2-3-1", "sausage": "fb-2-12-2-3-1",
    "sausages": "fb-2-12-2-3-1", "worsten": "fb-2-12-2-3-1",
    "rookworst": "fb-2-12-2-3-1", "salami": "fb-2-12-2-3-1",
    "vlees": "fb-2-12-2", "meat": "fb-2-12-2",
    "teriyaki sauces": "fb-2-4", "teriyaki sauce": "fb-2-4",
    "sauces": "fb-2-4", "saus": "fb-2-4",
    "kruiden": "fb-2-16-1", "specerijen": "fb-2-16-1",
}

# Slechts brede categorieën: zelfs wanneer het soort artikel herkenbaar is,
# blijft ras/bereiding/merk/variant bewust onbekend. Regels zijn semantische
# voedseltermen, geen op de privédata gebaseerde uitzonderingen per artikel.
NAME_RULES = (
    ("BEREIDE_AARDAPPEL", "fb-2-15-1-3", re.compile(
        r"\b(?:zoete\s+)?aardappel\w*\s+(?:frites|frite|frieten|friet)\b|\b(?:potato\s+)?fries\b")),
    ("BOUILLON", "fb-2-18", re.compile(r"\b(?:bouillon|broth|stock)\b")),
    ("ONTBIJTGRANEN", "fb-2-11-4", re.compile(
        r"\b(?:ontbijt\s*granen|ontbijtgranen|breakfast\s+cereals?|muesli|granola)\b")),
    ("KRUIDEN", "fb-2-16-1", re.compile(
        r"\b(?:uienpoeder|ui\s*poeder|knoflookpoeder|cayennepoeder|kerrie|specerijen|"
        r"rozemarijn|rosemary|venkelzaad|kruidenmix)\b")),
    ("VLEES", "fb-2-12-2", re.compile(
        r"\b(?:\w*gehakt\w*|\w*worst\w*|\w*salami\w*|\w*kipfilet\w*|"
        r"\w*kiphaas\w*|\w*runder\w*|\w*varkens\w*|\w*hamblok\w*|"
        r"\w*gehaktbal\w*)\b")),
    ("SAUS", "fb-2-4", re.compile(r"\b(?:\w*saus\w*|\w*sauce\w*|teriyaki)\b")),
)


def _shared_name_evidence(catalog_name, off_name):
    """Geef alleen duidelijk overlapbewijs, geen fuzzyscore of identiteitsoordeel."""
    one = [t for t in _norm(catalog_name).split() if len(t) >= 5]
    two = [t for t in _norm(off_name).split() if len(t) >= 5]
    if not one or not two:
        return False
    return any(a == b or (len(a) >= 7 and a in b) or (len(b) >= 7 and b in a)
               for a in one for b in two)


def _category_candidates(product, nl):
    by_id = defaultdict(list)
    # NL-categorietags die OFF zelf aan de product-GTIN gekoppeld heeft.
    texts = []
    for tag in product.get("category_tags") or []:
        if isinstance(tag, str) and tag.lower().startswith("nl:"):
            texts.append((tag[3:].replace("-", " "), "OFF nl: categorietag"))
    # OFF human-readable categorietekst (EN/NL, komma-gescheiden labels).
    for raw in str(product.get("categories") or "").split(","):
        raw = raw.strip()
        if raw:
            texts.append((re.sub(r"^[a-z]{2}:", "", raw, flags=re.I), "OFF categorieomschrijving"))

    nl_names = defaultdict(list)
    for code, row in nl.items():
        if code.startswith("fb-"):
            nl_names[_norm(row["naam"])].append(code)

    for value, origin in texts:
        normalized = _norm(value)
        if normalized in {"", "beleg", "grocerie", "grocery", "levensmiddelen", "food", "eten"}:
            continue
        for code in nl_names.get(normalized, []):
            by_id[code].append((3, f"{origin}: {safe(value, 45)} (Shopify NL letterlijk)"))
        for alias, code in OFF_CATEGORY_ALIASES.items():
            if normalized == _norm(alias):
                by_id[code].append((2, f"{origin}: {safe(value, 45)} (brede vertaalsleutel)"))
    return by_id


def _name_candidates(catalog_name, off_name):
    # Onderzoek alleen wanneer OFF de bestaande barcode exact herkende.
    # Exact dezelfde naam of een duidelijk gedeelde productstam is nodig;
    # zonder naamoverlap is een fallback op woorden ontoereikend.
    if not _shared_name_evidence(catalog_name, off_name):
        return []
    name = _norm(off_name)
    matched = []
    for label, code, pattern in NAME_RULES:
        if pattern.search(name):
            matched.append((code, f"OFF-productnaam '{safe(off_name, 70)}'; lokale brede soortregel {label}"))
    return matched


def _has_preparation_risk(text):
    words = _norm(text).split()
    return any(any(part in token for part in ("poeder", "puree", "frites", "frieten", "friet", "mashed"))
               for token in words)


def classify_proof7(product, catalog_name, indexes, baseline=None):
    """Vergelijk proof6 met extra, duidelijk lager gewogen OFF/NL/naamvoorstellen."""
    nl, _, cbs = indexes
    baseline = dict(baseline or classify_off_product(product, catalog_name, indexes))
    baseline_status = str(baseline.get("status") or "")
    # Bestaande voorstellen of expliciete conflicten nooit door een
    # onzekere nieuwe naamregel vervangen.
    if baseline_status != "GEEN_SHOPIFY_BIJPASSENDE_OFF_CATEGORIE":
        return {**baseline, "methode7": "BEHOUD_PROEF6", "was_voorstel6": bool(baseline.get("shopify_id")),
                "nieuw_voorstel7": False}

    # Een externe productnaam zonder enige productstamoverlap is geen veilig
    # vertrekpunt voor ook maar een brede categorie, zelfs met tags.
    off_name = str(product.get("product_name") or "").strip()
    if off_name and not _shared_name_evidence(catalog_name, off_name):
        return {**baseline, "methode7": "OFF_NAAMCONFLICT_GEEN_FALLBACK",
                "was_voorstel6": False, "nieuw_voorstel7": False}

    matched = _category_candidates(product, nl)
    # Gedroogde of bereide groenten niet als verse rauwe groenten voorstellen.
    if _has_preparation_risk(catalog_name) or _has_preparation_risk(product.get("product_name")):
        matched = {code: proof for code, proof in matched.items()
                   if not _is_parent("fb-2-10-8", code)}

    if matched:
        candidates = [(code, max(sources, key=lambda item: item[0]))
                      for code, sources in matched.items()]
        # Bewaar het specifiekste kind in dezelfde Shopify-tak.
        candidates = [row for row in candidates
                      if not any(row[0] != other[0] and _is_parent(row[0], other[0])
                                 for other in candidates)]
        candidates.sort(key=lambda row: (-row[1][0], -row[0].count("-"), row[0]))
        if len(candidates) == 1:
            code, (quality, source) = candidates[0]
            return {
                **baseline,
                "status": ("OFF_NL_LABEL_VOORSTEL" if quality == 3
                           else "OFF_TEKST_BREED_VOORSTEL"),
                "shopify_id": code, "shopify_pad": nl[code]["pad"],
                "cbs_vergelijking": _cbs_comparison(code, cbs),
                "bewijs": source, "methode7": "OFF_NL_OF_CATEGORIETEKST",
                "was_voorstel6": False, "nieuw_voorstel7": True,
            }
        return {
            **baseline, "status": "MEERDUIDIGE_OFF_CATEGORIE_VOORSTELLEN",
            "alternatieven": "; ".join(code for code, _ in candidates[:8]),
            "methode7": "OFF_CATEGORIE_AMBIGU", "was_voorstel6": False,
            "nieuw_voorstel7": False,
        }

    possibilities = _name_candidates(catalog_name, off_name)
    if len({code for code, _ in possibilities}) == 1:
        code, source = possibilities[0]
        return {
            **baseline, "status": "OFF_NAAM_BREED_CONTROLEREN",
            "shopify_id": code, "shopify_pad": nl[code]["pad"],
            "cbs_vergelijking": _cbs_comparison(code, cbs),
            "bewijs": source, "methode7": "ALLEEN_BREDE_NAAMSOORT",
            "was_voorstel6": False, "nieuw_voorstel7": True,
            "waarschuwing": ";".join(filter(None, (
                baseline.get("waarschuwing", ""), "NAAMVOORSTEL_NIET_BEVESTIGD"))),
        }
    if len(possibilities) > 1:
        return {
            **baseline, "status": "MEERDUIDIGE_NAAMSOORT",
            "alternatieven": "; ".join(sorted({code for code, _ in possibilities})),
            "methode7": "NAAMCONFLICT", "was_voorstel6": False,
            "nieuw_voorstel7": False,
        }
    return {**baseline, "methode7": "GEEN_VERANTWOORDE_EXTRA_MATCH",
            "was_voorstel6": False, "nieuw_voorstel7": False}
