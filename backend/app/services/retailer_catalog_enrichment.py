from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.product_taxonomy_store import normalize_taxonomy_text

CATALOG_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "lidl_catalog_enrichment_seed.json"


@dataclass(frozen=True)
class RetailerCatalogEnrichment:
    retailer_code: str
    matched: bool
    source_name: str
    source_product_code: str
    catalog_product_name: str
    brand: str
    category: str
    product_type: str
    quantity_label: str
    source_url: str
    confidence: float
    search_terms: list[str]


_EMPTY_ENRICHMENT = RetailerCatalogEnrichment(
    retailer_code="",
    matched=False,
    source_name="",
    source_product_code="",
    catalog_product_name="",
    brand="",
    category="",
    product_type="",
    quantity_label="",
    source_url="",
    confidence=0.0,
    search_terms=[],
)


@lru_cache(maxsize=1)
def _load_catalog_rules() -> tuple[dict[str, Any], ...]:
    if not CATALOG_SEED_PATH.exists():
        return tuple()
    payload = json.loads(CATALOG_SEED_PATH.read_text(encoding="utf-8"))
    return tuple(dict(rule) for rule in (payload.get("rules") or []))


def _dedupe_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_taxonomy_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
    return terms


def _rule_matches(normalized_text: str, rule: dict[str, Any]) -> bool:
    return any(
        normalize_taxonomy_text(term) in normalized_text
        for term in (rule.get("receipt_terms") or [])
        if normalize_taxonomy_text(term)
    )


def enrich_receipt_product_line(receipt_line_text: str | None, retailer_code: str | None = None) -> RetailerCatalogEnrichment:
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    if normalized_retailer != "lidl":
        return _EMPTY_ENRICHMENT

    normalized_text = normalize_taxonomy_text(receipt_line_text)
    if not normalized_text:
        return _EMPTY_ENRICHMENT

    for rule in _load_catalog_rules():
        if not _rule_matches(normalized_text, rule):
            continue

        search_terms = _dedupe_terms([
            rule.get("catalog_product_name") or "",
            rule.get("brand") or "",
            rule.get("category") or "",
            rule.get("product_type") or "",
            rule.get("quantity_label") or "",
            *(rule.get("search_terms") or []),
        ])
        return RetailerCatalogEnrichment(
            retailer_code="lidl",
            matched=True,
            source_name="lidl_catalog_enrichment",
            source_product_code=str(rule.get("source_product_code") or ""),
            catalog_product_name=str(rule.get("catalog_product_name") or ""),
            brand=str(rule.get("brand") or ""),
            category=str(rule.get("category") or ""),
            product_type=str(rule.get("product_type") or ""),
            quantity_label=str(rule.get("quantity_label") or ""),
            source_url=str(rule.get("source_url") or ""),
            confidence=float(rule.get("confidence") or 0.0),
            search_terms=search_terms,
        )

    return _EMPTY_ENRICHMENT


def enrich_receipt_product_line_dict(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    return asdict(enrich_receipt_product_line(receipt_line_text, retailer_code=retailer_code))
