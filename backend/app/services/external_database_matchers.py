from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

PROBABLE_CANDIDATE_THRESHOLD = 0.85
POSSIBLE_CANDIDATE_THRESHOLD = 0.70

SCORE_WEIGHTS = {
    "text_score": 0.30,
    "brand_score": 0.20,
    "product_type_score": 0.20,
    "quantity_score": 0.10,
    "variant_score": 0.10,
    "source_score": 0.10,
}


@dataclass(frozen=True)
class RetailerCandidateTemplate:
    candidate_name: str
    brand: str
    retailer_article_number: str
    product_type_terms: tuple[str, ...]
    quantity_label: str = ""
    variant: str = ""
    source_name: str = "lidl_product_group"
    source_url: str = ""
    source_score: float = 0.80


LIDL_TERM_LIBRARY: dict[str, tuple[str, ...]] = {
    "kruidenm": ("kruidenmix", "specerijenmix", "seasoning mix"),
    "mexicaanse": ("mexicaans", "mexican"),
    "taco saus": ("taco sauce", "sauce pour tacos"),
    "saus": ("sauce", "salsa"),
    "hot": ("scherp", "pikant"),
    "medium": ("mild", "middel"),
}

LIDL_HOUSE_BRANDS = (
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

LIDL_CANDIDATES = (
    RetailerCandidateTemplate(
        candidate_name="Kania Taco Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "taco specerijenmix", "taco seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Taco",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="Kania Burrito Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "burrito specerijenmix", "burrito seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Burrito",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="Kania Fajita Specerijenmix",
        brand="Kania/Kanig",
        retailer_article_number="21175",
        product_type_terms=("mexicaanse kruidenmix", "fajita specerijenmix", "fajita seasoning", "kruidenmix"),
        quantity_label="25-35 g",
        variant="Fajita",
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        candidate_name="El Tequito Taco Sauce hot",
        brand="El Tequito",
        retailer_article_number="20122386",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "hot sauce"),
        quantity_label="215 ml / 230 g",
        variant="Hot",
        source_name="lidl_product_candidate",
        source_score=0.85,
    ),
    RetailerCandidateTemplate(
        candidate_name="El Tequito Taco Sauce",
        brand="El Tequito",
        retailer_article_number="20122393",
        product_type_terms=("taco saus", "taco sauce", "sauce pour tacos", "salsa"),
        quantity_label="215 ml / 230 g",
        variant="",
        source_name="lidl_product_candidate",
        source_score=0.85,
    ),
)

RETAILER_CONFIG = {
    "lidl": {
        "retailer_code": "lidl",
        "retailer_name": "Lidl",
        "version": "external-databases-v1",
        "status": "active",
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "candidate_policy": "preview_only_until_user_confirmed_or_external_database_override",
        "term_library": LIDL_TERM_LIBRARY,
        "house_brands": LIDL_HOUSE_BRANDS,
        "score_weights": SCORE_WEIGHTS,
        "supported_examples": ["Mexicaanse kruidenm.", "Taco saus"],
    }
}


def normalize_match_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


def expand_terms_for_retailer(receipt_line_text: str, retailer_code: str) -> list[str]:
    normalized = normalize_match_text(receipt_line_text)
    expanded = {normalized}
    config = RETAILER_CONFIG.get(retailer_code, {})
    term_library = config.get("term_library", {})
    for source_term, replacements in term_library.items():
        source_term_normalized = normalize_match_text(source_term)
        if source_term_normalized and source_term_normalized in normalized:
            for replacement in replacements:
                expanded.add(normalized.replace(source_term_normalized, normalize_match_text(replacement)))
                expanded.add(normalize_match_text(replacement))
    return [item for item in sorted(expanded) if item]


def _text_similarity(left: str, right: str) -> float:
    left_normalized = normalize_match_text(left)
    right_normalized = normalize_match_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return 0.92
    return difflib.SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _best_text_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    values = [candidate.candidate_name, candidate.brand, candidate.variant, *candidate.product_type_terms]
    return max((_text_similarity(term, value) for term in expanded_terms for value in values), default=0.0)


def _brand_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    haystack = " ".join(expanded_terms)
    brand_tokens = [normalize_match_text(part) for part in re.split(r"[/,]", candidate.brand)]
    if any(token and token in haystack for token in brand_tokens):
        return 1.0
    if candidate.brand in {"Kania/Kanig", "El Tequito"}:
        return 0.86
    return 0.65


def _product_type_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    return max((_text_similarity(term, product_type) for term in expanded_terms for product_type in candidate.product_type_terms), default=0.0)


def _quantity_score(candidate: RetailerCandidateTemplate) -> float:
    return 0.80 if candidate.quantity_label else 0.50


def _variant_score(expanded_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    if not candidate.variant:
        return 0.75
    variant = normalize_match_text(candidate.variant)
    if any(variant and variant in term for term in expanded_terms):
        return 1.0
    # Lidl receipt lines often contain the product group but not the exact variant.
    if any("mexica" in term or "kruiden" in term for term in expanded_terms):
        return 0.82
    if any("taco" in term for term in expanded_terms) and variant == "hot":
        return 0.86
    return 0.70


def candidate_status_for_score(score: float) -> str:
    if score >= PROBABLE_CANDIDATE_THRESHOLD:
        return "probable_candidate"
    if score >= POSSIBLE_CANDIDATE_THRESHOLD:
        return "possible_candidate"
    return "weak_candidate"


def score_candidate(receipt_line_text: str, retailer_code: str, candidate: RetailerCandidateTemplate) -> dict[str, Any]:
    expanded_terms = expand_terms_for_retailer(receipt_line_text, retailer_code)
    breakdown = {
        "text_score": round(_best_text_score(expanded_terms, candidate), 3),
        "brand_score": round(_brand_score(expanded_terms, candidate), 3),
        "product_type_score": round(_product_type_score(expanded_terms, candidate), 3),
        "quantity_score": round(_quantity_score(candidate), 3),
        "variant_score": round(_variant_score(expanded_terms, candidate), 3),
        "source_score": round(candidate.source_score, 3),
    }
    score = sum(breakdown[key] * SCORE_WEIGHTS[key] for key in SCORE_WEIGHTS)
    score = round(score, 3)
    return {
        "candidate_name": candidate.candidate_name,
        "candidate_brand": candidate.brand,
        "candidate_source_name": candidate.source_name,
        "candidate_source_product_code": candidate.retailer_article_number,
        "retailer_article_number": candidate.retailer_article_number,
        "quantity_label": candidate.quantity_label,
        "variant": candidate.variant,
        "source_url": candidate.source_url,
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": candidate_status_for_score(score),
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
        "created_by": "external_database_lidl_matchpreview_v1",
    }


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    normalized_retailer = normalize_match_text(retailer_code)
    if normalized_retailer not in RETAILER_CONFIG:
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "expanded_terms": [],
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "candidates": [],
            "message": "Winkelketen wordt nog niet ondersteund in Externe databases v1.",
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
    expanded_terms = expand_terms_for_retailer(receipt_line_text, normalized_retailer)
    scored = [score_candidate(receipt_line_text, normalized_retailer, candidate) for candidate in LIDL_CANDIDATES]
    if not include_below_threshold:
        scored = [candidate for candidate in scored if candidate["score"] >= PROBABLE_CANDIDATE_THRESHOLD]
    scored.sort(key=lambda item: (-item["score"], item["candidate_name"]))
    return {
        "retailer_code": normalized_retailer,
        "receipt_line_text": receipt_line_text,
        "expanded_terms": expanded_terms,
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "possible_candidate_threshold": POSSIBLE_CANDIDATE_THRESHOLD,
        "candidates": scored,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def get_external_database_summary() -> dict[str, Any]:
    return {
        "module": "Externe databases",
        "version": "external-databases-v1",
        "supported_retailers": len(RETAILER_CONFIG),
        "active_retailers": [config["retailer_name"] for config in RETAILER_CONFIG.values() if config.get("status") == "active"],
        "candidate_policy": "preview_only_no_product_or_inventory_mutations",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def list_external_database_retailers() -> list[dict[str, Any]]:
    return [
        {
            "retailer_code": code,
            "retailer_name": config["retailer_name"],
            "status": config["status"],
            "version": config["version"],
            "probable_candidate_threshold": config["probable_candidate_threshold"],
            "supported_examples": config["supported_examples"],
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
        for code, config in RETAILER_CONFIG.items()
    ]
