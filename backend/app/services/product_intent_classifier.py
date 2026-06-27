from __future__ import annotations

from app.services.product_taxonomy_store import (
    classify_product_intent_from_taxonomy,
    contains_taxonomy_term,
    normalize_taxonomy_text,
)


def normalize_product_intent_text(value: str | None) -> str:
    return normalize_taxonomy_text(value)


def _contains_term(normalized_text: str, normalized_term: str) -> bool:
    return contains_taxonomy_term(normalized_text, normalized_term)


def classify_product_intent(text: str | None, retailer_code: str | None = None) -> str:
    """Classificeer productbetekenis via datagedreven taxonomie.

    Productnamen, synoniemen en retailer-termen horen in de database en in
    `backend/app/data/product_taxonomy_seed.json`, niet in Python-regellijsten.
    """
    return classify_product_intent_from_taxonomy(text, retailer_code=retailer_code)


def product_intent_match_score(receipt_text: str | None, candidate_text: str | None, retailer_code: str | None = None) -> float:
    receipt_intent = classify_product_intent(receipt_text, retailer_code=retailer_code)
    candidate_intent = classify_product_intent(candidate_text, retailer_code=retailer_code)

    # Onbekende intent is neutraal, niet negatief. Anders worden goede tekstuele
    # matches kunstmatig gehalveerd zodra de taxonomie de productsoort nog niet kent.
    if not receipt_intent or not candidate_intent:
        return 1.00

    if receipt_intent == candidate_intent:
        return 1.00

    return 0.00


def has_meaningful_product_intent_match(receipt_text: str | None, candidate_text: str | None, retailer_code: str | None = None) -> bool:
    receipt_intent = classify_product_intent(receipt_text, retailer_code=retailer_code)
    candidate_intent = classify_product_intent(candidate_text, retailer_code=retailer_code)

    # Onbekende intent blokkeert niet; dan blijft de gewone tekstscore leidend.
    if not receipt_intent or not candidate_intent:
        return True

    return receipt_intent == candidate_intent
