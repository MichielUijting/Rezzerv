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

