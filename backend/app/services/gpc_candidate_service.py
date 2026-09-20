from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Iterable

from app.services.product_taxonomy_store import (
    classify_product_intent_from_taxonomy,
    get_taxonomy_metadata_for_intent,
    load_taxonomy_rules,
    normalize_taxonomy_text,
)


_GENERIC_TOKENS = {
    "albert", "heijn", "ah", "jumbo", "lidl", "plus", "aldi",
    "product", "artikel", "food", "foods", "voedingsmiddelen",
    "organic", "biologisch", "bio", "the", "and", "with", "voor",
    "van", "met", "zonder", "een", "het", "de", "en",
}

_FIELD_WEIGHTS = {
    "product_name": 1.45,
    "category": 1.30,
    "external_product_name": 1.35,
    "external_category": 1.30,
    "external_categories": 1.15,
    "external_search_text": 1.10,
    "taxonomy_canonical_name": 1.55,
    "taxonomy_product_type": 1.50,
    "taxonomy_category": 1.05,
    "taxonomy_synonym": 1.15,
}

_HIERARCHY_WEIGHTS = {
    "brick_description": 1.00,
    "brick_description_en": 0.95,
    "class_description": 0.72,
    "family_description": 0.42,
    "segment_description": 0.18,
}


def _flatten_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_text(item))
        return result
    normalized = " ".join(str(value or "").strip().split())
    return [normalized] if normalized else []


def _meaningful_tokens(value: str) -> list[str]:
    normalized = normalize_taxonomy_text(value)
    tokens: list[str] = []
    for token in normalized.split():
        if len(token) < 3 or token in _GENERIC_TOKENS or token.isdigit():
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def _add_signal(
    signals: list[dict[str, Any]],
    seen: set[str],
    value: Any,
    *,
    source: str,
    weight: float,
) -> None:
    for text_value in _flatten_text(value):
        normalized = normalize_taxonomy_text(text_value)
        if not normalized or normalized in seen:
            continue
        tokens = _meaningful_tokens(normalized)
        if not tokens:
            continue
        seen.add(normalized)
        signals.append({
            "text": text_value,
            "normalized": normalized,
            "tokens": tokens,
            "source": source,
            "weight": float(weight),
        })


def build_product_signals(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build reusable product signals from canonical product and external metadata.

    Existing product-taxonomy synonyms are deliberately reused instead of adding
    a second hard-coded grocery vocabulary to the GPC classifier.
    """

    signals: list[dict[str, Any]] = []
    seen: set[str] = set()

    for field in (
        "product_name",
        "category",
        "external_product_name",
        "external_category",
        "external_categories",
        "external_search_text",
    ):
        _add_signal(
            signals,
            seen,
            metadata.get(field),
            source=field,
            weight=_FIELD_WEIGHTS[field],
        )

    intent_source = " ".join(
        _flatten_text(metadata.get("product_name"))
        + _flatten_text(metadata.get("category"))
        + _flatten_text(metadata.get("external_product_name"))
        + _flatten_text(metadata.get("external_category"))
        + _flatten_text(metadata.get("external_categories"))
        + _flatten_text(metadata.get("external_search_text"))
    )
    intent_key = classify_product_intent_from_taxonomy(intent_source)
    taxonomy_metadata = get_taxonomy_metadata_for_intent(intent_key)

    if intent_key:
        for field in ("canonical_name", "product_type", "category"):
            source = f"taxonomy_{field}"
            _add_signal(
                signals,
                seen,
                taxonomy_metadata.get(field),
                source=source,
                weight=_FIELD_WEIGHTS[source],
            )

        synonym_count = 0
        for rule in load_taxonomy_rules():
            if str(rule.get("intent_key") or "") != intent_key:
                continue
            _add_signal(
                signals,
                seen,
                rule.get("normalized_term"),
                source="taxonomy_synonym",
                weight=_FIELD_WEIGHTS["taxonomy_synonym"],
            )
            synonym_count += 1
            if synonym_count >= 16:
                break

    signals.sort(key=lambda row: (-float(row["weight"]), -len(row["tokens"]), row["normalized"]))
    return {
        "intent_key": intent_key,
        "taxonomy": taxonomy_metadata,
        "signals": signals[:28],
    }


def _candidate_haystacks(candidate: dict[str, Any]) -> dict[str, str]:
    return {
        field: normalize_taxonomy_text(candidate.get(field))
        for field in _HIERARCHY_WEIGHTS
    }


def _signal_match(signal: dict[str, Any], haystacks: dict[str, str]) -> tuple[float, str]:
    signal_text = str(signal.get("normalized") or "")
    signal_tokens = list(signal.get("tokens") or [])
    signal_weight = float(signal.get("weight") or 1.0)

    best_score = 0.0
    best_field = ""
    for field, hierarchy_weight in _HIERARCHY_WEIGHTS.items():
        haystack = haystacks.get(field) or ""
        if not haystack:
            continue

        location_score = 0.0
        if signal_text and signal_text == haystack:
            location_score += 7.0
        elif signal_text and signal_text in haystack:
            location_score += 5.0

        haystack_tokens = set(_meaningful_tokens(haystack))
        signal_token_set = set(signal_tokens)
        overlap = len(signal_token_set & haystack_tokens)
        if signal_tokens and overlap:
            location_score += 3.0 * (overlap / len(signal_token_set))
        elif signal_tokens and haystack_tokens:
            partial_overlap = 0
            for signal_token in signal_token_set:
                if len(signal_token) < 5:
                    continue
                if any(
                    len(haystack_token) >= 5
                    and (signal_token in haystack_token or haystack_token in signal_token)
                    for haystack_token in haystack_tokens
                ):
                    partial_overlap += 1
            if partial_overlap:
                location_score += 1.8 * (partial_overlap / len(signal_token_set))

        if len(signal_text) >= 5 and len(haystack) >= 5:
            fuzzy = SequenceMatcher(None, signal_text, haystack).ratio()
            if fuzzy >= 0.66:
                location_score += (fuzzy - 0.60) * 3.0

        weighted = location_score * hierarchy_weight * signal_weight
        if weighted > best_score:
            best_score = weighted
            best_field = field

    return best_score, best_field


def _confidence_label(value: float) -> str:
    if value >= 0.78:
        return "hoog"
    if value >= 0.58:
        return "redelijk"
    return "laag"


def rank_gpc_candidates(
    candidates: Iterable[dict[str, Any]],
    signal_bundle: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Rank official GPC rows and return at most five explainable candidates.

    The confidence value is an indicative match strength, not a probability.
    """

    signals = list(signal_bundle.get("signals") or [])
    if not signals:
        return []

    scored: list[dict[str, Any]] = []
    for raw_candidate in candidates:
        candidate = dict(raw_candidate)
        brick_code = str(candidate.get("brick_code") or "").strip()
        if not brick_code:
            continue

        haystacks = _candidate_haystacks(candidate)
        total = 0.0
        evidence: list[tuple[float, str, str]] = []
        matched_signal_keys: set[tuple[str, str]] = set()

        for signal in signals:
            score, field = _signal_match(signal, haystacks)
            if score <= 0:
                continue
            total += score
            key = (str(signal.get("normalized") or ""), field)
            if key not in matched_signal_keys:
                matched_signal_keys.add(key)
                evidence.append((score, str(signal.get("text") or ""), field))

        if total < 0.85:
            continue

        evidence.sort(key=lambda item: (-item[0], item[1]))
        candidate["_raw_match_score"] = total
        candidate["_evidence"] = evidence[:4]
        scored.append(candidate)

    if not scored:
        return []

    scored.sort(key=lambda row: (-float(row["_raw_match_score"]), str(row.get("brick_code") or "")))
    top_score = max(float(scored[0]["_raw_match_score"]), 0.01)

    result: list[dict[str, Any]] = []
    for candidate in scored[: max(1, min(int(limit), 5))]:
        raw_score = float(candidate.pop("_raw_match_score"))
        evidence = list(candidate.pop("_evidence"))
        relative = max(0.0, min(1.0, raw_score / top_score))
        absolute = min(0.91, 0.34 + min(0.57, raw_score * 0.032))
        confidence = round(max(0.30, min(0.94, absolute * (0.70 + (0.30 * relative)))), 3)

        matched_terms: list[str] = []
        matched_levels: list[str] = []
        for _, term, field in evidence:
            normalized_term = " ".join(str(term or "").split())
            if normalized_term and normalized_term not in matched_terms:
                matched_terms.append(normalized_term)
            level = field.replace("_description_en", "").replace("_description", "")
            if level and level not in matched_levels:
                matched_levels.append(level)

        reason_terms = ", ".join(matched_terms[:3])
        reason_levels = ", ".join(matched_levels[:2])
        if reason_terms:
            reason = f"Overeenkomst met productgegevens: {reason_terms}"
            if reason_levels:
                reason += f" ({reason_levels})"
        else:
            reason = "Overeenkomst met productgegevens en GPC-hiërarchie"

        candidate.update({
            "suggestion_source": "gpc_candidate_engine",
            "suggestion_reason": reason,
            "confidence": confidence,
            "confidence_label": _confidence_label(confidence),
            "match_strength_percent": int(round(confidence * 100)),
            "matched_terms": matched_terms[:4],
            "intent_key": str(signal_bundle.get("intent_key") or ""),
        })
        result.append(candidate)

    return result
