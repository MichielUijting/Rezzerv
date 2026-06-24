from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetailerTaxonomyEntry:
    retailer_code: str
    canonical_name: str
    brand: str
    retailer_article_number: str
    product_family: str
    product_type_terms: tuple[str, ...]
    receipt_terms: tuple[str, ...]
    off_query_terms: tuple[str, ...]
    quantity_label: str = ""
    variant: str = ""
    source_name: str = "retailer_taxonomy"
    source_url: str = ""
    source_score: float = 0.82


LIDL_TERM_LIBRARY: dict[str, tuple[str, ...]] = {
    "kruidenm": ("kruidenmix", "specerijenmix", "seasoning mix"),
    "mexicaanse": ("mexicaans", "mexican"),
    "taco saus": ("taco sauce", "sauce pour tacos"),
    "saus": ("sauce", "salsa"),
    "hot": ("scherp", "pikant"),
    "medium": ("mild", "middel"),

    # M2C2i-7: veilige Lidl-bontekstnormalisatie, geen fallback.
    "banaan": ("bananen", "banana", "fruit"),
    "bananen": ("banaan", "banana", "fruit"),
    "halfv melk": ("halfvolle melk", "melk halfvol", "zuivel"),
    "halfvolle melk": ("halfv melk", "melk halfvol", "zuivel"),
    "volle melk": ("melk vol", "zuivel"),
    "volkoren": ("volkoren brood", "brood volkoren"),
    "brood": ("volkoren brood", "bakkerij"),
    "eieren": ("ei", "vrije uitloop eieren"),
    "ei": ("eieren", "vrije uitloop eieren"),
    "appel": ("appels", "elstar appels", "fruit"),
    "appels": ("appel", "elstar appels", "fruit"),
    "spinazie": ("spinazie diepvries", "diepvriesgroente"),
    "pizza": ("pizza margherita", "diepvriespizza"),
    "havermout": ("ontbijt", "ontbijtgranen"),
    "water": ("mineraalwater", "mineraalwater bruisend"),
}

LIDL_HOUSE_BRANDS: tuple[str, ...] = (
    "Belbake",
    "Chef Select",
    "Culinea",
    "Dulano",
    "El Tequito",
    "Freeway",
    "Grafschafter",
    "Kanig",
    "Kania",
    "Milbona",
    "Snack Day",
)

LIDL_TAXONOMY: tuple[RetailerTaxonomyEntry, ...] = (
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Kania Taco Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_family="mexicaanse kruidenmix",
        product_type_terms=("mexicaanse kruidenmix", "taco specerijenmix", "taco seasoning", "kruidenmix"),
        receipt_terms=("mexicaanse kruiden", "mexicaanse kruidenm", "mexicaanse kruidenmix", "kruidenm", "taco"),
        off_query_terms=("kania taco specerijenmix", "kanig taco kruidenmix", "taco seasoning mix"),
        quantity_label="25-35 g",
        variant="Taco",
        source_name="lidl_taxonomy",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
        source_score=0.86,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Kania Burrito Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_family="mexicaanse kruidenmix",
        product_type_terms=("mexicaanse kruidenmix", "burrito specerijenmix", "burrito seasoning", "kruidenmix"),
        receipt_terms=("mexicaanse kruiden", "mexicaanse kruidenm", "mexicaanse kruidenmix", "kruidenm", "burrito"),
        off_query_terms=("kania burrito specerijenmix", "kanig burrito kruidenmix", "burrito seasoning mix"),
        quantity_label="25-35 g",
        variant="Burrito",
        source_name="lidl_taxonomy",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
        source_score=0.86,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Kania Fajita Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_family="mexicaanse kruidenmix",
        product_type_terms=("mexicaanse kruidenmix", "fajita specerijenmix", "fajita seasoning", "kruidenmix"),
        receipt_terms=("mexicaanse kruiden", "mexicaanse kruidenm", "mexicaanse kruidenmix", "kruidenm", "fajita"),
        off_query_terms=("kania fajita specerijenmix", "kanig fajita kruidenmix", "fajita seasoning mix"),
        quantity_label="25-35 g",
        variant="Fajita",
        source_name="lidl_taxonomy",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
        source_score=0.86,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="El Tequito Taco Sauce hot",
        brand="El Tequito",
        retailer_article_number="20122386",
        product_family="taco saus",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "hot sauce"),
        receipt_terms=("taco saus", "taco sauce", "hot", "pikant"),
        off_query_terms=("el tequito taco sauce hot", "taco sauce hot", "salsa taco hot"),
        quantity_label="215 ml / 230 g",
        variant="Hot",
        source_name="lidl_taxonomy",
        source_score=0.88,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="El Tequito Taco Sauce",
        brand="El Tequito",
        retailer_article_number="20122393",
        product_family="taco saus",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "salsa"),
        receipt_terms=("taco saus", "taco sauce", "medium", "salsa"),
        off_query_terms=("el tequito taco sauce", "taco sauce", "salsa taco"),
        quantity_label="215 ml / 230 g",
        variant="",
        source_name="lidl_taxonomy",
        source_score=0.88,
    ),
    # M2C2i-7: veilige productgroep-seedset voor betere Lidl-codeherkenning.
    # Dit zijn lokale externe productindex-codes/productgroepen; geen automatische productkoppeling.
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Bananen",
        brand="Lidl",
        retailer_article_number="LIDL-00026",
        product_family="fruit",
        product_type_terms=("banaan", "bananen", "banana", "fruit"),
        receipt_terms=("banaan", "bananen", "banana"),
        off_query_terms=("bananen", "banana", "lidl bananen"),
        quantity_label="1 kg",
        variant="",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Milbona Halfvolle melk",
        brand="Milbona",
        retailer_article_number="LIDL-00001",
        product_family="zuivel",
        product_type_terms=("halfvolle melk", "halfv melk", "melk halfvol", "zuivel"),
        receipt_terms=("halfvolle melk", "halfv melk", "melk halfvol"),
        off_query_terms=("halfvolle melk", "milbona halfvolle melk", "melk halfvol"),
        quantity_label="1 l",
        variant="Halfvol",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Volkoren brood",
        brand="Lidl",
        retailer_article_number="LIDL-00005",
        product_family="brood",
        product_type_terms=("volkoren brood", "brood volkoren", "bakkerij"),
        receipt_terms=("volkoren brood", "brood", "volkoren"),
        off_query_terms=("volkoren brood", "brood volkoren"),
        quantity_label="800 g",
        variant="Volkoren",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Eieren vrije uitloop",
        brand="Lidl",
        retailer_article_number="LIDL-00006",
        product_family="eieren",
        product_type_terms=("eieren", "ei", "vrije uitloop eieren"),
        receipt_terms=("eieren", "ei", "vrije uitloop"),
        off_query_terms=("eieren vrije uitloop", "lidl eieren"),
        quantity_label="10 stuks",
        variant="Vrije uitloop",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Elstar appels",
        brand="Lidl",
        retailer_article_number="LIDL-00027",
        product_family="fruit",
        product_type_terms=("appel", "appels", "elstar appels", "fruit"),
        receipt_terms=("appel", "appels", "elstar"),
        off_query_terms=("elstar appels", "lidl appels"),
        quantity_label="1.5 kg",
        variant="Elstar",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Spinazie diepvries",
        brand="Lidl",
        retailer_article_number="LIDL-00028",
        product_family="diepvriesgroente",
        product_type_terms=("spinazie", "spinazie diepvries", "diepvriesgroente"),
        receipt_terms=("spinazie", "spinazie diepvries"),
        off_query_terms=("spinazie diepvries", "lidl spinazie"),
        quantity_label="450 g",
        variant="Diepvries",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Pizza margherita",
        brand="Lidl",
        retailer_article_number="LIDL-00029",
        product_family="diepvriespizza",
        product_type_terms=("pizza", "pizza margherita", "diepvriespizza"),
        receipt_terms=("pizza", "margherita"),
        off_query_terms=("pizza margherita", "lidl pizza"),
        quantity_label="300 g",
        variant="Margherita",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Havermout",
        brand="Lidl",
        retailer_article_number="LIDL-00030",
        product_family="ontbijtgranen",
        product_type_terms=("havermout", "ontbijt", "ontbijtgranen"),
        receipt_terms=("havermout",),
        off_query_terms=("havermout", "lidl havermout"),
        quantity_label="500 g",
        variant="",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
    RetailerTaxonomyEntry(
        retailer_code="lidl",
        canonical_name="Lidl Mineraalwater bruisend",
        brand="Lidl",
        retailer_article_number="LIDL-00019",
        product_family="water",
        product_type_terms=("water", "mineraalwater", "mineraalwater bruisend"),
        receipt_terms=("water", "mineraalwater", "bruisend"),
        off_query_terms=("mineraalwater bruisend", "lidl water"),
        quantity_label="1.5 l",
        variant="Bruisend",
        source_name="lidl_product_group_seed",
        source_score=0.82,
    ),
)

RETAILER_TAXONOMIES: dict[str, tuple[RetailerTaxonomyEntry, ...]] = {
    "lidl": LIDL_TAXONOMY,
}

RETAILER_TERM_LIBRARIES: dict[str, dict[str, tuple[str, ...]]] = {
    "lidl": LIDL_TERM_LIBRARY,
}

RETAILER_HOUSE_BRANDS: dict[str, tuple[str, ...]] = {
    "lidl": LIDL_HOUSE_BRANDS,
}


def normalize_taxonomy_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def list_taxonomy_entries(retailer_code: str) -> tuple[RetailerTaxonomyEntry, ...]:
    return RETAILER_TAXONOMIES.get(normalize_taxonomy_text(retailer_code), tuple())


def expand_receipt_terms(receipt_line_text: str, retailer_code: str) -> list[str]:
    normalized = normalize_taxonomy_text(receipt_line_text)
    expanded = {normalized}
    term_library = RETAILER_TERM_LIBRARIES.get(normalize_taxonomy_text(retailer_code), {})
    for source_term, replacements in term_library.items():
        source_term_normalized = normalize_taxonomy_text(source_term)
        if source_term_normalized and source_term_normalized in normalized:
            for replacement in replacements:
                replacement_normalized = normalize_taxonomy_text(replacement)
                expanded.add(normalized.replace(source_term_normalized, replacement_normalized))
                expanded.add(replacement_normalized)
    return [item for item in sorted(expanded) if item]


def analyze_retailer_article_codes(receipt_line_text: str, retailer_code: str) -> dict[str, Any]:
    """Analyseer mogelijke retailer-artikelcodes voor een bonregel.

    Deze functie is alleen metadata/zoekverrijking:
    - geen productmutatie
    - geen household_article-mutatie
    - geen voorraadmutatie
    - geen beperking van kandidaatresultaten tot deze codes
    """
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    expanded_terms = set(expand_receipt_terms(receipt_line_text, normalized_retailer))
    matches: list[RetailerTaxonomyEntry] = []

    for entry in list_taxonomy_entries(normalized_retailer):
        # M2C2i-7: codeherkenning mag niet op brede categorie alleen matchen.
        # Productgroep/categorie zoals "fruit" of "zuivel" is zoekverrijking,
        # maar geen voldoende bewijs voor een retailer-artikelcode.
        entry_terms = {
            *entry.receipt_terms,
            entry.canonical_name,
            entry.retailer_article_number,
        }
        normalized_entry_terms = {
            normalize_taxonomy_text(term)
            for term in entry_terms
            if normalize_taxonomy_text(term)
        }
        if normalized_entry_terms & expanded_terms:
            matches.append(entry)

    article_codes = sorted({
        entry.retailer_article_number
        for entry in matches
        if normalize_taxonomy_text(entry.retailer_article_number)
    })

    off_query_terms = sorted({
        normalize_taxonomy_text(term)
        for entry in matches
        for term in entry.off_query_terms
        if normalize_taxonomy_text(term)
    })

    enriched_search_terms = {
        normalize_taxonomy_text(receipt_line_text),
        *expanded_terms,
        *off_query_terms,
    }

    # Artikelcodes zijn extra signalen, maar mogen de zoekresultaten niet beperken.
    for entry in matches:
        enriched_search_terms.update({
            normalize_taxonomy_text(entry.retailer_article_number),
            normalize_taxonomy_text(entry.canonical_name),
            normalize_taxonomy_text(entry.brand),
            normalize_taxonomy_text(entry.product_family),
            normalize_taxonomy_text(entry.variant),
            *[normalize_taxonomy_text(term) for term in entry.product_type_terms],
        })

    return {
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "retailer_article_codes": article_codes,
        "retailer_article_code_analysis": [
            {
                "retailer_article_number": entry.retailer_article_number,
                "canonical_name": entry.canonical_name,
                "brand": entry.brand,
                "variant": entry.variant,
                "product_family": entry.product_family,
                "quantity_label": entry.quantity_label,
                "source_name": entry.source_name,
                "source_url": entry.source_url,
            }
            for entry in matches
        ],
        "off_query_terms": off_query_terms,
        "index_search_terms": sorted(term for term in enriched_search_terms if term),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def build_off_query_terms(receipt_line_text: str, retailer_code: str) -> list[str]:
    """Return reviewable OFF search terms derived from retailer taxonomy.

    This function only prepares search terms. It deliberately performs no HTTP lookup,
    creates no products, creates no household articles and creates no inventory events.
    """
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    expanded_terms = expand_receipt_terms(receipt_line_text, normalized_retailer)
    entries = list_taxonomy_entries(normalized_retailer)
    query_terms: set[str] = set(expanded_terms)

    for entry in entries:
        entry_terms = {
            *entry.receipt_terms,
            *entry.product_type_terms,
            entry.canonical_name,
            entry.brand,
            entry.product_family,
            entry.variant,
        }
        normalized_entry_terms = {normalize_taxonomy_text(term) for term in entry_terms if normalize_taxonomy_text(term)}
        if normalized_entry_terms & set(expanded_terms):
            query_terms.update(normalize_taxonomy_text(term) for term in entry.off_query_terms)
            query_terms.add(normalize_taxonomy_text(entry.canonical_name))
            if entry.brand:
                query_terms.add(normalize_taxonomy_text(entry.brand))
            if entry.product_family:
                query_terms.add(normalize_taxonomy_text(entry.product_family))

    return [term for term in sorted(query_terms) if term]


def get_taxonomy_summary(retailer_code: str) -> dict[str, Any]:
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    entries = list_taxonomy_entries(normalized_retailer)
    return {
        "retailer_code": normalized_retailer,
        "taxonomy_entry_count": len(entries),
        "term_library_count": len(RETAILER_TERM_LIBRARIES.get(normalized_retailer, {})),
        "house_brand_count": len(RETAILER_HOUSE_BRANDS.get(normalized_retailer, tuple())),
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
