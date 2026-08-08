from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.product_taxonomy_store import _seed_payload, contains_taxonomy_term, normalize_taxonomy_text


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
    source_name: str = "product_taxonomy_seed"
    source_url: str = ""
    source_score: float = 0.82


def _taxonomy_items() -> list[dict[str, Any]]:
    return [dict(item) for item in (_seed_payload().get("taxonomy") or [])]


def _retailer_items(retailer_code: str) -> list[dict[str, Any]]:
    normalized = normalize_taxonomy_text(retailer_code)
    return [dict(item) for item in (_seed_payload().get("retailer_receipt_terms") or []) if normalize_taxonomy_text(item.get("retailer_code")) == normalized]


def _terms_for_intent(intent_key: str, retailer_code: str) -> tuple[str, ...]:
    terms: set[str] = set()
    for item in _taxonomy_items():
        if str(item.get("intent_key") or "") != intent_key:
            continue
        terms.add(str(item.get("canonical_name") or ""))
        terms.update(str(value or "") for value in (item.get("synonyms") or []))
    for item in _retailer_items(retailer_code):
        if str(item.get("intent_key") or "") != intent_key:
            continue
        terms.add(str(item.get("receipt_term") or ""))
        terms.add(str(item.get("normalized_term") or ""))
    return tuple(sorted({normalize_taxonomy_text(term) for term in terms if normalize_taxonomy_text(term)}))


def list_taxonomy_entries(retailer_code: str) -> tuple[RetailerTaxonomyEntry, ...]:
    retailer = normalize_taxonomy_text(retailer_code)
    entries: list[RetailerTaxonomyEntry] = []
    for item in _taxonomy_items():
        intent_key = str(item.get("intent_key") or "").strip()
        if not intent_key:
            continue
        terms = _terms_for_intent(intent_key, retailer)
        if not terms:
            continue
        entries.append(RetailerTaxonomyEntry(
            retailer_code=retailer,
            canonical_name=str(item.get("canonical_name") or intent_key).strip(),
            brand="",
            retailer_article_number=f"{retailer}:{intent_key}",
            product_family=str(item.get("category") or "").strip(),
            product_type_terms=terms,
            receipt_terms=terms,
            off_query_terms=terms,
        ))
    return tuple(entries)


def expand_receipt_terms(receipt_line_text: str, retailer_code: str) -> list[str]:
    normalized = normalize_taxonomy_text(receipt_line_text)
    expanded = {normalized}
    for entry in list_taxonomy_entries(retailer_code):
        if any(contains_taxonomy_term(normalized, term) for term in entry.receipt_terms):
            expanded.update(entry.product_type_terms)
            expanded.update(entry.off_query_terms)
    return [item for item in sorted(expanded) if item]


def analyze_retailer_article_codes(receipt_line_text: str, retailer_code: str) -> dict[str, Any]:
    retailer = normalize_taxonomy_text(retailer_code)
    expanded_terms = set(expand_receipt_terms(receipt_line_text, retailer))
    matches = []
    for entry in list_taxonomy_entries(retailer):
        entry_terms = {*entry.receipt_terms, normalize_taxonomy_text(entry.canonical_name), normalize_taxonomy_text(entry.retailer_article_number)}
        if entry_terms & expanded_terms:
            matches.append(entry)
    off_query_terms = sorted({term for entry in matches for term in entry.off_query_terms if term})
    index_search_terms = sorted({normalize_taxonomy_text(receipt_line_text), *expanded_terms, *off_query_terms})
    return {
        "retailer_code": retailer,
        "receipt_line_text": receipt_line_text,
        "retailer_article_codes": [entry.retailer_article_number for entry in matches],
        "retailer_article_code_analysis": [{
            "retailer_article_number": entry.retailer_article_number,
            "canonical_name": entry.canonical_name,
            "brand": entry.brand,
            "variant": entry.variant,
            "product_family": entry.product_family,
            "quantity_label": entry.quantity_label,
            "source_name": entry.source_name,
            "source_url": entry.source_url,
        } for entry in matches],
        "off_query_terms": off_query_terms,
        "index_search_terms": index_search_terms,
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def build_off_query_terms(receipt_line_text: str, retailer_code: str) -> list[str]:
    return analyze_retailer_article_codes(receipt_line_text, retailer_code).get("index_search_terms", [])


def get_taxonomy_summary(retailer_code: str) -> dict[str, Any]:
    retailer = normalize_taxonomy_text(retailer_code)
    return {
        "retailer_code": retailer,
        "taxonomy_entry_count": len(list_taxonomy_entries(retailer)),
        "term_library_count": 0,
        "house_brand_count": 0,
        "source": "product_taxonomy_seed",
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }
