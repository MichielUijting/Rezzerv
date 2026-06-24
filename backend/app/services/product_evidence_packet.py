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


def _field(candidate: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = candidate.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = {token for token in normalize_taxonomy_text(left).split() if len(token) >= 3}
    right_tokens = {token for token in normalize_taxonomy_text(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _numeric_overlap(left: str | None, right: str | None) -> float:
    left_numbers = {token for token in normalize_taxonomy_text(left).split() if any(char.isdigit() for char in token)}
    right_numbers = {token for token in normalize_taxonomy_text(right).split() if any(char.isdigit() for char in token)}
    if not left_numbers or not right_numbers:
        return 0.0
    return 1.0 if left_numbers & right_numbers else 0.0


def _candidate_code(candidate: dict[str, Any]) -> str:
    return _field(candidate, [
        "candidate_source_product_code",
        "source_product_code",
        "retailer_article_number",
        "gtin",
        "ean",
        "code",
        "barcode",
    ])


def score_candidate_with_product_evidence(candidate: dict[str, Any], evidence_packet: dict[str, Any]) -> dict[str, Any]:
    """Verhoog OFF-kandidaatscore op basis van veilig productbewijs.

    Zonder GTIN blijft de evidence-boost begrensd op 0.85, behalve wanneer de
    kandidaat exact hetzelfde retailer-artikelnummer of dezelfde code draagt.
    De functie muteert geen product-, artikel- of voorraadtabellen.
    """
    if not evidence_packet.get("matched"):
        return dict(candidate)

    candidate_name = _field(candidate, ["candidate_name", "product_name", "name", "generic_name"])
    candidate_brand = _field(candidate, ["candidate_brand", "brand", "brands"])
    candidate_quantity = _field(candidate, ["quantity_label", "quantity", "net_content", "packaging"])
    candidate_code = normalize_taxonomy_text(_candidate_code(candidate))
    retailer_article_code = normalize_taxonomy_text(evidence_packet.get("retailer_article_code"))
    gtin = normalize_taxonomy_text(evidence_packet.get("gtin"))

    code_match = 1.0 if candidate_code and candidate_code in {retailer_article_code, gtin} else 0.0
    brand_match = max(
        (1.0 if normalize_taxonomy_text(term) and normalize_taxonomy_text(term) in normalize_taxonomy_text(candidate_brand + " " + candidate_name) else 0.0)
        for term in evidence_packet.get("brand_terms") or [""]
    )
    name_match = _token_overlap(evidence_packet.get("canonical_name"), candidate_name)
    quantity_match = _numeric_overlap(evidence_packet.get("quantity_label"), candidate_quantity)

    evidence_score = round((code_match * 0.40) + (brand_match * 0.20) + (name_match * 0.25) + (quantity_match * 0.15), 3)
    result = dict(candidate)
    result["product_evidence_packet"] = evidence_packet
    result["product_evidence_score"] = evidence_score
    result.setdefault("score_breakdown", {})["product_evidence_score"] = evidence_score

    current_score = float(result.get("score") or 0.0)
    target_score = current_score
    if code_match >= 1.0:
        target_score = max(target_score, 0.95)
    elif evidence_score >= 0.55:
        target_score = max(target_score, min(0.85, current_score + 0.20))

    if target_score > current_score:
        result["score"] = round(target_score, 3)
        result["candidate_status"] = "probable_candidate" if target_score >= 0.85 else result.get("candidate_status", "possible_candidate")
        result["is_probable"] = target_score >= 0.85
        result["product_evidence_boost_applied"] = True
        result.setdefault("score_breakdown", {})["product_evidence_boost_score"] = round(target_score, 3)

    result["creates_global_product"] = False
    result["creates_household_article"] = False
    result["creates_inventory_event"] = False
    return result


def apply_product_evidence_to_candidates(
    receipt_line_text: str | None,
    retailer_code: str | None,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_packet = build_product_evidence_packet_dict(receipt_line_text, retailer_code=retailer_code)
    rescored = [score_candidate_with_product_evidence(candidate, evidence_packet) for candidate in candidates]
    return sorted(rescored, key=lambda item: (-float(item.get("score") or 0.0), str(item.get("candidate_name") or "")))
