from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.services.product_intent_classifier import classify_product_intent
from app.services.product_taxonomy_store import normalize_taxonomy_text


QUANTITY_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[,.]\d+)?)\s*(?P<unit>kg|g|gr|gram|l|lt|liter|ml|cl|st|stuk|stuks|x)",
    flags=re.IGNORECASE,
)

PRODUCT_TYPE_BY_INTENT_PREFIX = {
    "zuivel.melk": "melk",
    "zuivel.yoghurt": "yoghurt",
    "zuivel.vla": "vla",
    "zuivel.kaas": "kaas",
    "zuivel.creme_fraiche": "crème fraîche",
    "fruit.banaan": "banaan",
    "fruit.appel": "appel",
    "bakkerij.brood": "brood",
    "groente.spinazie": "spinazie",
    "groente.courgette": "courgette",
    "groente.zoete_aardappel": "zoete aardappel",
    "groente.aardappel": "aardappel",
    "eieren.ei": "ei",
    "graan.rijst": "rijst",
    "saus.tomatensaus": "tomatensaus",
    "groente.tomaat": "tomaat",
    "maaltijd.pizza": "pizza",
    "kruiden.specerijenmix": "specerijenmix",
    "vleeswaren.ham": "ham",
    "vleeswaren.kipfilet": "kipfilet",
    "drank.frisdrank": "frisdrank",
    "pasta.droog": "pasta",
    "snack.chips": "chips",
    "ontbijt.muesli": "muesli",
    "ontbijt.havermout": "havermout",
    "drank.water": "water",
}

CATEGORY_BY_INTENT_PREFIX = {
    "zuivel.": "zuivel",
    "fruit.": "fruit",
    "bakkerij.": "bakkerij",
    "groente.": "groente",
    "eieren.": "eieren",
    "graan.": "graan",
    "saus.": "saus",
    "maaltijd.": "maaltijd",
    "kruiden.": "kruiden",
    "vleeswaren.": "vleeswaren",
    "drank.": "drank",
    "pasta.": "pasta",
    "snack.": "snack",
    "ontbijt.": "ontbijt",
}

VARIANT_TERMS = (
    "gouda",
    "gerasp",
    "geraspt",
    "rasp",
    "raspkaas",
    "italiaans",
    "mozzarella",
    "parmezaan",
    "grana padano",
    "emmentaler",
    "jong",
    "jonge",
    "jong belegen",
    "belegen",
    "oud",
    "48",
    "30",
    "halfvol",
    "halfvolle",
    "vol",
    "volle",
    "mager",
    "magere",
    "naturel",
    "paprika",
    "mild",
    "hot",
    "zero",
    "bruisend",
    "ongezouten",
    "volkoren",
    "vrije uitloop",
    "diepvries",
    "basilicum",
    "linguine",
)

STOPWORDS = {
    "de",
    "het",
    "een",
    "en",
    "of",
    "met",
    "voor",
    "van",
    "lidl",
    "ah",
    "aldi",
    "jumbo",
    "plus",
    "picnic",
}


@dataclass(frozen=True)
class ReceiptProductAnalysis:
    raw_text: str
    normalized_text: str
    retailer_code: str
    product_intent: str
    category: str
    product_type: str
    variant_terms: list[str]
    quantity_amount: str
    quantity_unit: str
    quantity_label: str
    searchable_terms: list[str]
    requires_user_confirmation: bool


def _category_for_intent(intent_key: str) -> str:
    for prefix, category in CATEGORY_BY_INTENT_PREFIX.items():
        if intent_key.startswith(prefix):
            return category
    return ""


def _product_type_for_intent(intent_key: str) -> str:
    return PRODUCT_TYPE_BY_INTENT_PREFIX.get(intent_key, "")


def _extract_quantity(normalized_text: str) -> tuple[str, str, str]:
    match = QUANTITY_PATTERN.search(normalized_text)
    if not match:
        return "", "", ""

    amount = match.group("amount").replace(",", ".")
    unit = match.group("unit").lower()
    normalized_unit = {
        "gr": "g",
        "gram": "g",
        "lt": "l",
        "liter": "l",
        "stuk": "st",
        "stuks": "st",
    }.get(unit, unit)
    return amount, normalized_unit, f"{amount} {normalized_unit}"


def _extract_variant_terms(normalized_text: str) -> list[str]:
    variants: list[str] = []
    for term in VARIANT_TERMS:
        normalized_term = normalize_taxonomy_text(term)
        if normalized_term and normalized_term in normalized_text:
            variants.append(normalized_term)
    return variants


def _deduplicate(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_taxonomy_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def analyze_receipt_product_line(receipt_line_text: str | None, retailer_code: str | None = None) -> ReceiptProductAnalysis:
    raw_text = str(receipt_line_text or "").strip()
    normalized_text = normalize_taxonomy_text(raw_text)
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    product_intent = classify_product_intent(normalized_text, retailer_code=normalized_retailer)
    category = _category_for_intent(product_intent)
    product_type = _product_type_for_intent(product_intent)
    quantity_amount, quantity_unit, quantity_label = _extract_quantity(normalized_text)
    variant_terms = _extract_variant_terms(normalized_text)

    tokens = [token for token in normalized_text.split() if len(token) >= 3 and token not in STOPWORDS]
    searchable_terms = _deduplicate([
        normalized_text,
        product_intent,
        category,
        product_type,
        *variant_terms,
        quantity_label,
        *tokens,
    ])

    return ReceiptProductAnalysis(
        raw_text=raw_text,
        normalized_text=normalized_text,
        retailer_code=normalized_retailer,
        product_intent=product_intent,
        category=category,
        product_type=product_type,
        variant_terms=variant_terms,
        quantity_amount=quantity_amount,
        quantity_unit=quantity_unit,
        quantity_label=quantity_label,
        searchable_terms=searchable_terms,
        requires_user_confirmation=not bool(product_intent),
    )


def analyze_receipt_product_line_dict(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, object]:
    return asdict(analyze_receipt_product_line(receipt_line_text, retailer_code=retailer_code))
