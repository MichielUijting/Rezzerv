from __future__ import annotations

import difflib
import re
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
        "candidate_policy": "off_index_or_explicit_off_search_only",
        "supported_examples": ["Raadpleeg OFF vanuit bonartikel"],
    }
}


def normalize_match_text(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace(".", " ")
    normalized = re.sub(r"[^a-z0-9áéíóúàèìòùäëïöüçñ\s-]+", " ", normalized, flags=re.IGNORECASE)
    return " ".join(normalized.split())


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


def candidate_status_for_score(score: float) -> str:
    if score >= PROBABLE_CANDIDATE_THRESHOLD:
        return "probable_candidate"
    if score >= POSSIBLE_CANDIDATE_THRESHOLD:
        return "possible_candidate"
    return "weak_candidate"


def match_retailer_receipt_line(retailer_code: str, receipt_line_text: str, include_below_threshold: bool = True) -> dict[str, Any]:
    """Match external candidates without legacy product taxonomy seed fallback.

    The active candidate path is the real OFF index matcher. Static Lidl/product
    taxonomy seed candidates were intentionally removed because OFF is now the
    authoritative candidate source for this screen.
    """
    from app.services.external_database_off_index_matchers import match_retailer_receipt_line as off_index_matcher

    return off_index_matcher(
        retailer_code=retailer_code,
        receipt_line_text=receipt_line_text,
        include_below_threshold=include_below_threshold,
    )


def get_external_database_summary() -> dict[str, Any]:
    return {
        "module": "Externe databases",
        "version": "external-databases-v1",
        "supported_retailers": len(RETAILER_CONFIG),
        "active_retailers": [config["retailer_name"] for config in RETAILER_CONFIG.values() if config.get("status") == "active"],
        "candidate_policy": "off_index_or_explicit_off_search_only",
        "uses_product_taxonomy_seed_candidates": False,
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
            "candidate_policy": config["candidate_policy"],
            "uses_product_taxonomy_seed_candidates": False,
            "creates_global_product": False,
            "creates_household_article": False,
            "creates_inventory_event": False,
        }
        for code, config in RETAILER_CONFIG.items()
    ]
