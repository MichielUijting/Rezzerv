"""Conservatieve OFF->Shopify-aggregatie voor gecodeerde Catalogusartikelen.

Shopify is een taxonomie, geen barcode-index. De OFF-productmatch op de reeds
aanwezige GTIN is het bewijs voor de *bronvermelding*, niet voor de inhoudelijke
juistheid van een voorgestelde Shopify-categorie. GEEN automatische opslag.
"""

from collections import defaultdict
import gzip
import json
import re
import unicodedata

from tools.inhuis_taxonomy_proof5_core import (
    DATA, SHOPIFY_TO_ECO, load_references, safe,
)


SOURCE_VERSION = "2026-08"

# Expliciete, *brede* interpretatie van OFF-tags die geen letterlijke Shopify-
# labelmatch opleveren. Bijvoorbeeld 'groenten' bewijst NIET dat ze vers zijn.
# Alle resultaten, ook exacte labels, blijven een niet-bevestigd voorstel.
OFF_TO_SHOPIFY_BROAD = {
    "fruits": "fb-2-10", "fruit": "fb-2-10",
    "fruits-based-foods": "fb-2-10", "vegetables": "fb-2-10",
    "vegetable-based-foods": "fb-2-10", "nuts": "fb-2-13",
    "seeds": "fb-2-13", "milks": "fb-2-6", "milk": "fb-2-6",
    "cheeses": "fb-2-6", "yogurts": "fb-2-6",
    "meats": "fb-2-12-2", "breads": "fb-2-1",
    "pastas": "fb-2-14", "snacks": "fb-2-17",
    "soft-drinks": "fb-1-12", "waters": "fb-1-16",
    "fruit-juices": "fb-1-7", "herbs": "fb-2-16-1",
    "spices": "fb-2-16-1", "mixed-herbs": "fb-2-16-1",
    "mashed-potatoes": "fb-2-15-1-3",
}
GENERIC_OFF_TAGS = {
    "foods", "beverages", "food", "plant-based-foods-and-beverages",
    "plant-based-foods", "en:plant-based-foods", "plant-based-beverages",
    "animal-products", "groceries", "products", "processed-foods",
}
PROCESSED_POTATO_WORDS = {"mashed", "puree", "pureed", "frites", "fries", "chips", "prepared", "cooked"}
EXTRA_CBS_COMPARE = (
    ("fb-2-13", "011680"),  # noten
    ("fb-2-16-1", "011940"),  # kruiden, specerijen
    ("fb-2-15-1-3", "011790"),  # bereide aardappelbijgerechten (slechts benadering)
)


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    parts = re.findall(r"[a-z0-9]+", value.replace("&", " and "))
    result = []
    for word in parts:
        if word.endswith("ies") and len(word) > 5:
            word = word[:-3] + "y"
        elif word.endswith("oes") and len(word) > 5:
            word = word[:-2]
        elif word.endswith("es") and len(word) > 5 and word.endswith(("ches", "shes", "sses")):
            word = word[:-2]
        elif word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
            word = word[:-1]
        result.append(word)
    return " ".join(result)


def _tag_slug(value):
    text = str(value or "").strip().lower()
    if not text.startswith("en:"):
        return ""
    return text[3:]


def _is_parent(parent, child):
    return child == parent or child.startswith(parent + "-")


def load_indexes():
    shopify, cbs = load_references()
    with gzip.open(DATA / "shopify_2026_08_en_food.json.gz", "rt", encoding="utf-8") as handle:
        en = json.load(handle)
    nl_by_id = {row["id"]: row for row in shopify["categorieen"]}
    if en.get("versie") != SOURCE_VERSION or len(en.get("categorieen") or []) != 764:
        raise RuntimeError("VEILIG GESTOPT: verkeerde Shopify EN referentieversie")
    en_by_id = {row["id"]: row for row in en["categorieen"]}
    if any(cat_id not in nl_by_id for cat_id in en_by_id) or len(en_by_id) != 764:
        raise RuntimeError("VEILIG GESTOPT: Engelse Shopify-index is niet consistent met NL")
    by_name = defaultdict(list)
    for row in en["categorieen"]:
        normalized = _norm(row["en"])
        if len(normalized) >= 3:
            by_name[normalized].append(row["id"])
    cbs_by_id = {row["code"]: row["naam"] for row in cbs["codes"]}
    return nl_by_id, by_name, cbs_by_id


def _cbs_comparison(cat_id, cbs_by_id):
    for prefix, code in EXTRA_CBS_COMPARE + SHOPIFY_TO_ECO:
        if _is_parent(prefix, cat_id):
            name = cbs_by_id.get(code)
            return f"{code} {name}" if name else ""
    return ""


def classify_off_product(off_product, catalog_name, indexes):
    """Geef maximaal één hoofdvoorstel, anders expliciete onduidelijkheid.

    Veronderstelt reeds een exact door OFF bevestigde, valide GTIN-match.
    Geen inferentie uit uitsluitend de Catalogusnaam.
    """
    nl, en_names, cbs = indexes
    tags = [_tag_slug(tag) for tag in (off_product.get("category_tags") or [])]
    tags = sorted({tag for tag in tags if tag and tag not in GENERIC_OFF_TAGS})
    processed_potato = any(any(term in tag for term in PROCESSED_POTATO_WORDS)
                           for tag in tags if "potato" in tag)
    by_cat = {}
    for tag in tags:
        direct = en_names.get(_norm(tag.replace("-", " ")), [])
        # OFF potato-tag 'potatoes' mag verwerkte aardappelproducten nooit
        # stilzwijgend categoriseren als VERS.
        if processed_potato:
            direct = [cat_id for cat_id in direct if not _is_parent("fb-2-10-8", cat_id)]
        for cat_id in direct:
            entry = (3, f"OFF en:{tag}; Engelse Shopify-categorienaam letterlijk")
            if cat_id not in by_cat or entry[0] > by_cat[cat_id][0]:
                by_cat[cat_id] = entry
        mapped = OFF_TO_SHOPIFY_BROAD.get(tag)
        if mapped:
            if processed_potato and _is_parent("fb-2-10-8", mapped):
                continue
            entry = (1 if tag == "mashed-potatoes" else 2,
                     f"OFF en:{tag}; lokale brede vertaalsleutel")
            if mapped not in by_cat or entry[0] > by_cat[mapped][0]:
                by_cat[mapped] = entry

    # Houd de meest specifieke categorie, tenzij een andere onafhankelijke
    # tak van de hiërarchie een conflict veroorzaakt.
    candidates = [(cat_id, score, source) for cat_id, (score, source) in by_cat.items()]
    candidates = [entry for entry in candidates
                  if not any(entry[0] != other[0] and _is_parent(entry[0], other[0])
                             for other in candidates)]
    candidates.sort(key=lambda row: (-row[1], -row[0].count("-"), row[0]))
    unresolved = len(candidates) != 1
    if not candidates:
        status = "GEEN_SHOPIFY_BIJPASSENDE_OFF_CATEGORIE"
    elif unresolved:
        status = "MEERDUIDIGE_SHOPIFY_CATEGORIE"
    elif candidates[0][1] == 3:
        status = "OFF_LABEL_DIRECT_SHOPIFY_VOORSTEL"
    else:
        status = "OFF_BREDE_VERTALING_VOORSTEL"
    chosen = candidates[0][0] if not unresolved else ""

    # Naamvergelijking detecteert alleen flagrante discrepanties. Geen
    # inhoudelijke productverificatie en geen fuzzy 'zekerheidsscore'.
    off_name = str(off_product.get("product_name") or "")
    catalog_tokens = {w for w in _norm(catalog_name).split() if len(w) >= 5}
    off_tokens = {w for w in _norm(off_name).split() if len(w) >= 5}
    placeholder = bool(re.fullmatch(r"product\s+\d{8,14}", str(catalog_name or "").strip(), re.I))
    warning = ""
    if off_name and catalog_tokens and off_tokens and not placeholder and not catalog_tokens.intersection(off_tokens):
        warning = "CONTROLEER_NAAMVERSCHIL"
    if any(term in _norm(catalog_name).split() for term in ("bobotie", "mix", "maaltijd", "ovenschotel")):
        warning = ";".join(filter(None, (warning, "SAMENGESTELD_PRODUCT_CONTROLEREN")))
    return {
        "status": status,
        "shopify_id": chosen,
        "shopify_pad": nl[chosen]["pad"] if chosen else "",
        "cbs_vergelijking": _cbs_comparison(chosen, cbs) if chosen else "",
        "bewijs": candidates[0][2] if chosen else "",
        "alternatieven": "; ".join(cat_id for cat_id, _, _ in candidates[:8]) if unresolved else "",
        "off_tags": ", ".join(tags[:15]),
        "waarschuwing": warning,
        "off_naam": safe(off_name, 100),
        "off_categorie": safe(off_product.get("categories"), 180),
    }
