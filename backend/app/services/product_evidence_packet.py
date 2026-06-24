from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.services.product_taxonomy_store import normalize_taxonomy_text
from app.services.retailer_catalog_enrichment import enrich_receipt_product_line


@dataclass(frozen=True)
class ProductEvidencePacket:
    retailer_code: str
    receipt_line_text: str
    matched: bool
    canonical_name: str
    brand: str
    brand_terms: list[str]
    retailer: str
    retailer_article_code: str
    category: str
    product_type: str
    quantity_label: str
    gtin: str | None
    source_url: str
    evidence_sources: list[str]
    missing_evidence_fields: list[str]
    off_query_terms: list[str]
    off_score_signals: dict[str, Any]
    recommended_next_action: str
    creates_global_product: bool
    creates_household_article: bool
    creates_inventory_event: bool


def _brand_terms(brand: str | None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for part in str(brand or "").replace("/", ",").split(","):
        value = part.strip()
        normalized = normalize_taxonomy_text(value)
        if value and normalized and normalized not in seen:
            seen.add(normalized)
            terms.append(value)
    return terms


def _dedupe_terms(values: list[str | None]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_taxonomy_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return terms


def _safe_flags() -> dict[str, bool]:
    return {
        "creates_global_product": False,
        "creates_household_article": False,
        "creates_inventory_event": False,
    }


def build_product_evidence_packet(receipt_line_text: str | None, retailer_code: str | None = None) -> ProductEvidencePacket:
    normalized_retailer = normalize_taxonomy_text(retailer_code)
    raw_text = str(receipt_line_text or "").strip()
    enrichment = enrich_receipt_product_line(raw_text, retailer_code=normalized_retailer)

    if not enrichment.matched:
        return ProductEvidencePacket(
            retailer_code=normalized_retailer,
            receipt_line_text=raw_text,
            matched=False,
            canonical_name=raw_text,
            brand="",
            brand_terms=[],
            retailer=normalized_retailer,
            retailer_article_code="",
            category="",
            product_type="",
            quantity_label="",
            gtin=None,
            source_url="",
            evidence_sources=["receipt"],
            missing_evidence_fields=["gtin", "quantity_label", "ingredients_text", "nutrition_text"],
            off_query_terms=_dedupe_terms([raw_text]),
            off_score_signals={
                "has_gtin": False,
                "has_retailer_catalog_match": False,
                "has_brand": False,
                "has_quantity": False,
                "has_ingredients": False,
                "has_nutrition": False,
            },
            recommended_next_action="scan_package_for_gtin",
            **_safe_flags(),
        )

    brand_terms = _brand_terms(enrichment.brand)
    evidence_sources = ["receipt", "retailer_catalog_rule"]
    if enrichment.source_url:
        evidence_sources.append("retailer_product_page")

    return ProductEvidencePacket(
        retailer_code=enrichment.retailer_code,
        receipt_line_text=raw_text,
        matched=True,
        canonical_name=enrichment.catalog_product_name,
        brand=enrichment.brand,
        brand_terms=brand_terms,
        retailer="Lidl",
        retailer_article_code=enrichment.source_product_code,
        category=enrichment.category,
        product_type=enrichment.product_type,
        quantity_label=enrichment.quantity_label,
        gtin=None,
        source_url=enrichment.source_url,
        evidence_sources=evidence_sources,
        missing_evidence_fields=["gtin", "ingredients_text", "nutrition_text"],
        off_query_terms=_dedupe_terms([
            enrichment.catalog_product_name,
            *brand_terms,
            enrichment.category,
            enrichment.product_type,
            enrichment.quantity_label,
            *enrichment.search_terms,
        ]),
        off_score_signals={
            "has_gtin": False,
            "has_retailer_catalog_match": True,
            "has_brand": bool(brand_terms),
            "has_quantity": bool(enrichment.quantity_label),
            "has_ingredients": False,
            "has_nutrition": False,
            "catalog_confidence": enrichment.confidence,
            "off_match_ceiling_without_gtin": 0.85,
        },
        recommended_next_action="scan_package_for_gtin",
        **_safe_flags(),
    )


def build_product_evidence_packet_dict(receipt_line_text: str | None, retailer_code: str | None = None) -> dict[str, Any]:
    return asdict(build_product_evidence_packet(receipt_line_text, retailer_code=retailer_code))
