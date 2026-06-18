from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


PROBABLE_CANDIDATE_THRESHOLD = 0.85


@dataclass(frozen=True)
class RetailerTermRule:
    term: str
    expansions: tuple[str, ...]


@dataclass(frozen=True)
class RetailerCandidateTemplate:
    name: str
    brand: str | None
    retailer_article_number: str | None
    source_name: str
    product_type: str
    quantity_label: str | None
    variant: str | None
    terms: tuple[str, ...]
    source_url: str | None = None


LIDL_TERM_LIBRARY: tuple[RetailerTermRule, ...] = (
    RetailerTermRule("kruidenm", ("kruidenmix", "specerijenmix", "seasoning mix")),
    RetailerTermRule("mexicaanse", ("mexicaans", "mexican")),
    RetailerTermRule("taco saus", ("taco sauce", "sauce pour tacos")),
    RetailerTermRule("saus", ("sauce", "salsa")),
    RetailerTermRule("hot", ("scherp", "pikant")),
    RetailerTermRule("medium", ("mild", "middel")),
)


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


LIDL_CANDIDATE_TEMPLATES: tuple[RetailerCandidateTemplate, ...] = (
    RetailerCandidateTemplate(
        name="Kania Taco Specerijenmix",
        brand="Kania",
        retailer_article_number="21175",
        source_name="lidl_product_group",
        product_type="kruidenmix",
        quantity_label="25-35 g",
        variant="Taco",
        terms=("mexicaanse kruidenmix", "taco specerijenmix", "taco seasoning", "kania taco"),
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        name="Kania Burrito Specerijenmix",
        brand="Kania",
        retailer_article_number="21175",
        source_name="lidl_product_group",
        product_type="kruidenmix",
        quantity_label="25-35 g",
        variant="Burrito",
        terms=("mexicaanse kruidenmix", "burrito specerijenmix", "burrito seasoning", "kania burrito"),
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        name="Kania Fajita Specerijenmix",
        brand="Kania",
        retailer_article_number="21175",
        source_name="lidl_product_group",
        product_type="kruidenmix",
        quantity_label="25-35 g",
        variant="Fajita",
        terms=("mexicaanse kruidenmix", "fajita specerijenmix", "fajita seasoning", "kania fajita"),
        source_url="https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
    ),
    RetailerCandidateTemplate(
        name="El Tequito Taco Sauce hot",
        brand="El Tequito",
        retailer_article_number="20122386",
        source_name="lidl_product_group",
        product_type="taco sauce",
        quantity_label="215 ml / 230 g",
        variant="hot",
        terms=("taco saus", "taco sauce", "sauce pour tacos", "el tequito taco sauce hot"),
    ),
    RetailerCandidateTemplate(
        name="El Tequito Taco Sauce",
        brand="El Tequito",
        retailer_article_number="20122393",
        source_name="lidl_product_group",
        product_type="taco sauce",
        quantity_label="215 ml / 230 g",
        variant=None,
        terms=("taco saus", "taco sauce", "sauce pour tacos", "el tequito taco sauce"),
    ),
)


RETAILER_ALGORITHM_CONFIG: dict[str, dict[str, Any]] = {
    "lidl": {
        "retailer_code": "lidl",
        "retailer_name": "Lidl",
        "version": "external-databases-v1",
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "candidate_policy": "candidate_only_until_user_confirmed_or_external_database_override",
        "external_database_override_allowed": True,
        "creates_global_product": False,
        "creates_household_article": False,
        "supports_retailer_site_lookup": True,
        "retailer_site_url_template": "https://www.lidl.nl/p/{slug}/p{retailer_article_number}",
        "retailer_site_lookup_status": "configured_for_later_collection_not_called_by_default",
        "score_weights": {
            "text_score": 0.30,
            "brand_score": 0.20,
            "product_type_score": 0.20,
            "quantity_score": 0.10,
            "variant_score": 0.10,
            "source_score": 0.10,
        },
        "term_library": [
            {"term": rule.term, "expansions": list(rule.expansions)}
            for rule in LIDL_TERM_LIBRARY
        ],
        "house_brands": list(LIDL_HOUSE_BRANDS),
    }
}


def normalize_match_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def expand_terms_for_retailer(retailer_code: str, value: Any) -> list[str]:
    normalized = normalize_match_text(value)
    if not normalized:
        return []
    expanded = {normalized}
    rules = LIDL_TERM_LIBRARY if retailer_code == "lidl" else ()
    for rule in rules:
        rule_key = normalize_match_text(rule.term)
        if rule_key and rule_key in normalized:
            for expansion in rule.expansions:
                expanded.add(normalized.replace(rule_key, normalize_match_text(expansion)))
                expanded.add(normalize_match_text(expansion))
    return sorted(part for part in expanded if part)


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.95
    left_tokens = {part for part in left.split() if len(part) >= 3}
    right_tokens = {part for part in right.split() if len(part) >= 3}
    if not left_tokens or not right_tokens:
        return SequenceMatcher(None, left, right).ratio()
    overlap = len(left_tokens.intersection(right_tokens)) / max(1, len(left_tokens))
    return max(overlap, SequenceMatcher(None, left, right).ratio())


def _best_text_score(search_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    candidate_terms = [candidate.name, candidate.product_type, candidate.variant or "", *(candidate.terms or ())]
    normalized_candidate_terms = [normalize_match_text(item) for item in candidate_terms if normalize_match_text(item)]
    if not search_terms or not normalized_candidate_terms:
        return 0.0
    return max(_similarity(query, candidate_term) for query in search_terms for candidate_term in normalized_candidate_terms)


def _brand_score(retailer_code: str, candidate: RetailerCandidateTemplate) -> float:
    if retailer_code == "lidl" and candidate.brand in LIDL_HOUSE_BRANDS:
        return 0.90
    if candidate.brand:
        return 0.70
    return 0.40


def _product_type_score(search_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    haystack = " ".join(search_terms)
    product_type = normalize_match_text(candidate.product_type)
    if product_type and product_type in haystack:
        return 1.0
    if product_type == "kruidenmix" and any(term in haystack for term in ("specerijenmix", "seasoning mix", "kruidenmix")):
        return 0.95
    if product_type == "taco sauce" and any(term in haystack for term in ("taco saus", "taco sauce", "sauce pour tacos")):
        return 0.95
    return 0.65 if product_type else 0.40


def _quantity_score(candidate: RetailerCandidateTemplate) -> float:
    return 0.90 if candidate.quantity_label else 0.50


def _variant_score(search_terms: list[str], candidate: RetailerCandidateTemplate) -> float:
    if not candidate.variant:
        return 0.50
    variant = normalize_match_text(candidate.variant)
    haystack = " ".join(search_terms)
    if variant in haystack:
        return 1.0
    if candidate.retailer_article_number == "21175":
        return 0.70
    return 0.50


def _source_score(candidate: RetailerCandidateTemplate) -> float:
    if candidate.source_name == "open_food_facts":
        return 0.85
    if candidate.source_name == "lidl_product_group":
        return 0.80
    return 0.60


def score_retailer_candidate(retailer_code: str, receipt_line_text: str, candidate: RetailerCandidateTemplate) -> dict[str, Any]:
    config = RETAILER_ALGORITHM_CONFIG.get(retailer_code, RETAILER_ALGORITHM_CONFIG["lidl"])
    weights = config["score_weights"]
    search_terms = expand_terms_for_retailer(retailer_code, receipt_line_text)
    breakdown = {
        "text_score": round(_best_text_score(search_terms, candidate), 3),
        "brand_score": round(_brand_score(retailer_code, candidate), 3),
        "product_type_score": round(_product_type_score(search_terms, candidate), 3),
        "quantity_score": round(_quantity_score(candidate), 3),
        "variant_score": round(_variant_score(search_terms, candidate), 3),
        "source_score": round(_source_score(candidate), 3),
    }
    total = sum(float(breakdown[key]) * float(weights[key]) for key in weights)
    score = round(total, 3)
    status = "probable_candidate" if score >= PROBABLE_CANDIDATE_THRESHOLD else "possible_candidate" if score >= 0.70 else "weak_candidate"
    return {
        "candidate_name": candidate.name,
        "candidate_brand": candidate.brand,
        "candidate_source_name": candidate.source_name,
        "candidate_source_product_code": candidate.retailer_article_number,
        "retailer_article_number": candidate.retailer_article_number,
        "quantity_label": candidate.quantity_label,
        "variant": candidate.variant,
        "source_url": candidate.source_url,
        "score": score,
        "score_breakdown": breakdown,
        "candidate_status": status,
        "is_probable": score >= PROBABLE_CANDIDATE_THRESHOLD,
        "is_user_confirmed": False,
        "is_external_database_override": False,
        "external_database_can_override": True,
        "created_by": "auto_lidl_candidate_matcher" if retailer_code == "lidl" else "auto_retailer_candidate_matcher",
    }


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    normalized_retailer = normalize_match_text(retailer_code or "lidl") or "lidl"
    if normalized_retailer != "lidl":
        return {
            "retailer_code": normalized_retailer,
            "receipt_line_text": receipt_line_text,
            "normalized_terms": expand_terms_for_retailer(normalized_retailer, receipt_line_text),
            "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "candidates": [],
            "message": "Voor deze winkelketen is nog geen algoritme gespecificeerd.",
        }
    scored = [score_retailer_candidate("lidl", receipt_line_text, candidate) for candidate in LIDL_CANDIDATE_TEMPLATES]
    scored.sort(key=lambda item: (-float(item["score"]), str(item["candidate_name"])))
    if not include_below_threshold:
        scored = [item for item in scored if item["is_probable"]]
    return {
        "retailer_code": "lidl",
        "receipt_line_text": receipt_line_text,
        "normalized_terms": expand_terms_for_retailer("lidl", receipt_line_text),
        "probable_candidate_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "candidates": scored,
        "creates_global_product": False,
        "creates_household_article": False,
    }


def get_external_database_configuration() -> dict[str, Any]:
    return {
        "version": "external-databases-v1",
        "default_threshold": PROBABLE_CANDIDATE_THRESHOLD,
        "retailers": list(RETAILER_ALGORITHM_CONFIG.values()),
        "supported_retailer_codes": sorted(RETAILER_ALGORITHM_CONFIG.keys()),
        "candidate_lifecycle": {
            "auto_status": "probable_candidate",
            "threshold": PROBABLE_CANDIDATE_THRESHOLD,
            "may_be_overwritten_by": "Externe database",
            "may_not_overwrite": ["user_confirmed", "external_database_override"],
        },
    }
