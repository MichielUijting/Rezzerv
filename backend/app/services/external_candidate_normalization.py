from __future__ import annotations

from typing import Any

from app.services.product_taxonomy_store import normalize_taxonomy_text

SOURCE_PRIORITY = {
    "lidl_catalog_enrichment": 100,
    "retailer_alias_learning": 95,
    "lidl_product_group": 90,
    "product_taxonomy_seed": 80,
    "OFF-index": 70,
    "receipt_product_intent_fallback": 10,
    "receipt_unresolved_fallback": 0,
}


def _field(candidate: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = candidate.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _source_name(candidate: dict[str, Any]) -> str:
    return _field(candidate, ["candidate_source_name", "source_name"])


def _source_code(candidate: dict[str, Any]) -> str:
    return _field(candidate, ["candidate_source_product_code", "source_product_code", "retailer_article_number", "gtin", "ean", "code"])


def _token_overlap(left: str | None, right: str | None) -> float:
    left_tokens = {token for token in normalize_taxonomy_text(left).split() if len(token) >= 3}
    right_tokens = {token for token in normalize_taxonomy_text(right).split() if len(token) >= 3}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))


def _priority(candidate: dict[str, Any]) -> int:
    return SOURCE_PRIORITY.get(_source_name(candidate), 50)


def _identity_key(candidate: dict[str, Any], evidence_packet: dict[str, Any] | None = None) -> str:
    source_code = normalize_taxonomy_text(_source_code(candidate))
    source_name = normalize_taxonomy_text(_source_name(candidate))
    candidate_name = normalize_taxonomy_text(_field(candidate, ["candidate_name", "product_name", "name"]))

    evidence_packet = evidence_packet or {}
    evidence_code = normalize_taxonomy_text(evidence_packet.get("retailer_article_code"))
    evidence_name = normalize_taxonomy_text(evidence_packet.get("canonical_name"))

    if evidence_packet.get("matched") and evidence_code:
        if source_code == evidence_code or _token_overlap(candidate_name, evidence_name) >= 0.45:
            return f"evidence:{evidence_code}"

    if source_code and source_code != "unknown":
        return f"code:{source_code}"

    return f"name:{source_name}:{candidate_name}"


def _merge_candidates(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    primary, secondary = (incoming, existing) if _priority(incoming) > _priority(existing) else (existing, incoming)
    result = dict(primary)

    result["score"] = round(max(float(existing.get("score") or 0.0), float(incoming.get("score") or 0.0)), 3)
    result["candidate_status"] = "probable_candidate" if result["score"] >= 0.85 else primary.get("candidate_status", "possible_candidate")
    result["is_probable"] = result["score"] >= 0.85

    evidence_packet = primary.get("product_evidence_packet") or secondary.get("product_evidence_packet")
    if evidence_packet:
        result["product_evidence_packet"] = evidence_packet

    source_names = []
    source_codes = []
    for candidate in [existing, incoming]:
        source_name = _source_name(candidate)
        source_code = _source_code(candidate)
        if source_name and source_name not in source_names:
            source_names.append(source_name)
        if source_code and source_code not in source_codes:
            source_codes.append(source_code)

    result["merged_source_names"] = source_names
    result["merged_source_product_codes"] = source_codes
    result["deduplicated_candidate_count"] = int(existing.get("deduplicated_candidate_count") or 1) + int(incoming.get("deduplicated_candidate_count") or 1)
    result.setdefault("score_breakdown", {})["deduplicated_candidate_count"] = result["deduplicated_candidate_count"]

    for flag in ["creates_global_product", "creates_household_article", "creates_inventory_event"]:
        result[flag] = False

    return result


def normalize_external_candidates(candidates: list[dict[str, Any]], evidence_packet: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        item = dict(candidate)
        item.setdefault("candidate_source_name", item.get("source_name") or "external_product_index")
        item.setdefault("candidate_source_product_code", item.get("source_product_code") or item.get("retailer_article_number") or "unknown")
        item.setdefault("source_name", item.get("candidate_source_name"))
        item.setdefault("source_product_code", item.get("candidate_source_product_code"))
        item.setdefault("retailer_article_number", item.get("candidate_source_product_code"))
        for flag in ["creates_global_product", "creates_household_article", "creates_inventory_event"]:
            item[flag] = False

        key = _identity_key(item, evidence_packet=evidence_packet)
        if key in grouped:
            grouped[key] = _merge_candidates(grouped[key], item)
        else:
            item["deduplicated_candidate_count"] = 1
            grouped[key] = item

    result = list(grouped.values())
    result.sort(key=lambda item: (-float(item.get("score") or 0.0), -_priority(item), str(item.get("candidate_name") or "")))
    return result
