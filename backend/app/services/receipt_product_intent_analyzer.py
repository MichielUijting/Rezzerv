from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.services.product_intent_classifier import classify_product_intent
from app.services.product_taxonomy_store import (
    contains_taxonomy_term,
    get_taxonomy_metadata_for_intent,
    load_product_variant_terms,
    normalize_taxonomy_text,
)


QUANTITY_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[,.]\d+)?)\s*(?P<unit>kg|g|gr|gram|l|lt|liter|ml|cl|st|stuk|stuks|x)",
    flags=re.IGNORECASE,
)

STOPWORDS = {"de", "het", "een", "en", "of", "met", "voor", "van"}


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


def _extract_variant_matches(normalized_text: str, product_intent: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rule in load_product_variant_terms(product_intent or None):
        normalized_term = str(rule.get("normalized_variant_term") or "")
        if normalized_term and contains_taxonomy_term(normalized_text, normalized_term):
            matches.append(dict(rule))
    return matches


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


def _build_searchable_terms(
    normalized_text: str,
    product_intent: str,
    category: str,
    product_type: str,
    variant_matches: list[dict[str, Any]],
    quantity_label: str,
) -> list[str]:
    tokens = [token for token in normalized_text.split() if len(token) >= 3 and token not in STOPWORDS]
    variant_terms = [str(match.get("normalized_variant_term") or "") for match in variant_matches]
    variant_search_terms: list[str] = []

    for match in variant_matches:
        variant = str(match.get("normalized_variant_term") or "")
        variant_search_terms.extend(str(term or "") for term in (match.get("search_terms") or []))
        if variant and product_type and not contains_taxonomy_term(variant, product_type):
            variant_search_terms.append(f"{variant} {product_type}")

    return _deduplicate([
        normalized_text,
        product_intent,
        category,
        product_type,
        *variant_terms,
        *variant_search_terms,
        quantity_label,
        *tokens,
    ])


def analyze_receipt_product_line(receipt_line_text: str | None, retailer_code: str | None = None) -> ReceiptProductAnalysis:
    raw_text = str(receipt_line_text or "").strip()
    normalized_text = normalize_taxonomy_text(raw_text)
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    product_intent = classify_product_intent(normalized_text, retailer_code=normalized_retailer)
    taxonomy_metadata = get_taxonomy_metadata_for_intent(product_intent)
    category = taxonomy_metadata.get("category") or ""
    product_type = taxonomy_metadata.get("product_type") or ""
    quantity_amount, quantity_unit, quantity_label = _extract_quantity(normalized_text)
    variant_matches = _extract_variant_matches(normalized_text, product_intent)
    variant_terms = _deduplicate([str(match.get("normalized_variant_term") or "") for match in variant_matches])
    searchable_terms = _build_searchable_terms(
        normalized_text=normalized_text,
        product_intent=product_intent,
        category=category,
        product_type=product_type,
        variant_matches=variant_matches,
        quantity_label=quantity_label,
    )

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
