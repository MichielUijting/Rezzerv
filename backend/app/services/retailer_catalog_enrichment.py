from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.services.product_taxonomy_store import normalize_taxonomy_text


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


LIDL_CATALOG_RULES: tuple[dict[str, Any], ...] = (
    {
        "receipt_terms": ("mexicaanse kruidenm", "mexicaanse kruidenmix", "taco kruidenmix", "burrito kruidenmix", "fajita kruidenmix"),
        "source_product_code": "21175",
        "catalog_product_name": "Kania Mexicaanse kruidenmix",
        "brand": "Kania/Kanig",
        "category": "Kruiden",
        "product_type": "Specerijenmix",
        "quantity_label": "25-35 g",
        "source_url": "https://www.lidl.nl/p/mexicaanse-kruidenmix/p21175",
        "confidence": 0.95,
        "search_terms": (
            "Kania Mexicaanse kruidenmix",
            "Kanig Mexicaanse kruidenmix",
            "mexicaanse kruidenmix taco burrito fajita",
            "taco seasoning mix",
            "burrito seasoning mix",
            "fajita seasoning mix",
            "specerijenmix",
        ),
    },
    {
        "receipt_terms": ("taco saus", "taco saus mild", "taco saus hot"),
        "source_product_code": "lidl:taco-saus",
        "catalog_product_name": "Lidl Taco saus",
        "brand": "Lidl",
        "category": "Mexicaans",
        "product_type": "Taco saus",
        "quantity_label": "230 g",
        "source_url": "",
        "confidence": 0.85,
        "search_terms": (
            "taco saus mild",
            "taco saus hot",
            "salsa taco sauce",
            "mexicaanse saus",
        ),
    },
    {
        "receipt_terms": ("gouda belegen gerasp", "gouda belegen", "gerasp", "rasp kaas"),
        "source_product_code": "lidl:gouda-belegen-gerasp",
        "catalog_product_name": "Lidl Gouda belegen geraspte kaas",
        "brand": "Lidl Zuivel",
        "category": "Zuivel",
        "product_type": "Kaas",
        "quantity_label": "200 g",
        "source_url": "",
        "confidence": 0.90,
        "search_terms": (
            "gouda belegen geraspte kaas",
            "geraspte kaas gouda belegen",
            "gouda grated cheese",
            "belegen kaas geraspt",
        ),
    },
    {
        "receipt_terms": ("crème fraiche 30", "creme fraiche 30", "cr me fraiche 30", "creme frache 30", "crème frache 30"),
        "source_product_code": "lidl:creme-fraiche-30",
        "catalog_product_name": "Lidl Crème fraîche 30%",
        "brand": "Lidl Zuivel",
        "category": "Zuivel",
        "product_type": "Crème fraîche",
        "quantity_label": "200 g",
        "source_url": "",
        "confidence": 0.90,
        "search_terms": (
            "creme fraiche 30%",
            "crème fraîche 30%",
            "sour cream 30%",
            "creme frache 30",
        ),
    },
    {
        "receipt_terms": ("duurzame basmati rijst", "basmati rijst"),
        "source_product_code": "lidl:basmati-rijst",
        "catalog_product_name": "Lidl Basmati rijst",
        "brand": "Lidl Rijst",
        "category": "Rijst",
        "product_type": "Rijst",
        "quantity_label": "1 kg",
        "source_url": "",
        "confidence": 0.90,
        "search_terms": (
            "basmati rijst",
            "duurzame basmati rijst",
            "basmati rice",
        ),
    },
    {
        "receipt_terms": ("gebronsde pasta linguin", "gebronste pasta linguine", "pasta linguine", "linguine"),
        "source_product_code": "lidl:linguine",
        "catalog_product_name": "Lidl Linguine pasta",
        "brand": "Lidl Pasta",
        "category": "Pasta",
        "product_type": "Droge pasta",
        "quantity_label": "500 g",
        "source_url": "",
        "confidence": 0.90,
        "search_terms": (
            "linguine pasta",
            "gebronste pasta linguine",
            "gebronsde pasta linguin",
            "pasta linguine",
        ),
    },
)


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

    for rule in LIDL_CATALOG_RULES:
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
