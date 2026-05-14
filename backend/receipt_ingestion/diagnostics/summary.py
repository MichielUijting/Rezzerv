from __future__ import annotations

from typing import Any, Dict, List

from ..contracts import ParserRow, ReviewSuggestion


GOOD_IMAGE_THRESHOLD = 0.75
MODERATE_IMAGE_THRESHOLD = 0.45


def build_diagnostics_summary(
    payload: Dict[str, Any],
    parser_rows: List[ParserRow],
    review_suggestions: List[ReviewSuggestion],
) -> Dict[str, Any]:
    metadata = payload.get('metadata', {}) or {}
    has_usable_legacy_diagnostics = _has_usable_legacy_poc_diagnostics(metadata, payload)

    image_quality = _derive_image_quality(metadata)
    ocr_quality = _derive_ocr_quality(metadata, parser_rows, has_usable_legacy_diagnostics)
    parser_confidence = _derive_parser_confidence(parser_rows)
    safety_level = _derive_safety_level(review_suggestions)
    dominant_issue = _derive_dominant_issue(metadata, parser_rows, has_usable_legacy_diagnostics)
    recommended_user_action = _derive_recommended_user_action(
        image_quality=image_quality,
        parser_confidence=parser_confidence,
        parser_rows=parser_rows,
        review_suggestions=review_suggestions,
        dominant_issue=dominant_issue,
        has_usable_legacy_diagnostics=has_usable_legacy_diagnostics,
    )

    return {
        'image_quality': image_quality,
        'ocr_quality': ocr_quality,
        'parser_confidence': parser_confidence,
        'safety_level': safety_level,
        'dominant_issue': dominant_issue,
        'recommended_user_action': recommended_user_action,
        'has_usable_legacy_poc_diagnostics': has_usable_legacy_diagnostics,
    }


def _has_usable_legacy_poc_diagnostics(metadata: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    if metadata.get('product_block_rescue_diagnostics'):
        return True

    if metadata.get('line_type_counts'):
        return True

    if 'detected_rows' in metadata:
        return True

    if metadata.get('line_diagnostics'):
        return True

    if metadata.get('product_block'):
        return True

    has_schema_version = bool(payload.get('schema_version'))
    has_source_file = bool(metadata.get('source_file') or payload.get('source_file'))

    return has_schema_version and has_source_file


def _derive_image_quality(metadata: Dict[str, Any]) -> str:
    diagnostics = metadata.get('document_isolation_enhancement_diagnostics', {}) or {}
    variants = diagnostics.get('variants', []) or []

    if not variants:
        return 'unknown'

    best_score = 0.0
    for variant in variants:
        quality = float(variant.get('local_contrast_score') or 0.0)
        sharpness = float(variant.get('text_sharpness_score') or 0.0)
        score = (quality + sharpness) / 2.0
        best_score = max(best_score, score)

    if best_score >= GOOD_IMAGE_THRESHOLD:
        return 'good'

    if best_score >= MODERATE_IMAGE_THRESHOLD:
        return 'moderate'

    return 'poor'


def _derive_ocr_quality(
    metadata: Dict[str, Any],
    parser_rows: List[ParserRow],
    has_usable_legacy_diagnostics: bool,
) -> str:
    normalization = metadata.get('ocr_structural_normalization', {}) or {}
    groups = normalization.get('normalized_line_groups', []) or []

    if parser_rows:
        return 'good'

    if len(groups) >= 5:
        return 'moderate'

    if groups:
        return 'poor'

    if has_usable_legacy_diagnostics:
        return 'moderate'

    return 'unknown'


def _derive_parser_confidence(parser_rows: List[ParserRow]) -> str:
    if not parser_rows:
        return 'low'

    confidences = [row.confidence for row in parser_rows if row.confidence is not None]

    if not confidences:
        return 'medium'

    avg_confidence = sum(confidences) / len(confidences)

    if avg_confidence >= 0.85:
        return 'high'

    if avg_confidence >= 0.60:
        return 'medium'

    return 'low'


def _derive_safety_level(review_suggestions: List[ReviewSuggestion]) -> str:
    if not review_suggestions:
        return 'unknown'

    low_risk_count = sum(1 for s in review_suggestions if s.risk_level == 'low')

    if low_risk_count == len(review_suggestions):
        return 'safe'

    if low_risk_count > 0:
        return 'review_needed'

    return 'blocked'


def _derive_dominant_issue(
    metadata: Dict[str, Any],
    parser_rows: List[ParserRow],
    has_usable_legacy_diagnostics: bool,
) -> str:
    governance = metadata.get('pre_ocr_image_correction_governance', {}) or {}
    findings = governance.get('image_quality_findings', {}) or {}

    if findings.get('shadow_risk') in {'high', 'medium'}:
        return 'image_quality'

    normalization = metadata.get('ocr_structural_normalization', {}) or {}
    rejected_groups = normalization.get('rejected_groups', []) or []

    if rejected_groups:
        return 'ocr_structure'

    if not parser_rows and has_usable_legacy_diagnostics:
        return 'ocr_structure'

    if not parser_rows:
        return 'missing_parser_rows'

    return 'none'


def _derive_recommended_user_action(
    image_quality: str,
    parser_confidence: str,
    parser_rows: List[ParserRow],
    review_suggestions: List[ReviewSuggestion],
    dominant_issue: str,
    has_usable_legacy_diagnostics: bool,
) -> str:
    if image_quality == 'poor':
        return 'rescan'

    if parser_rows and parser_confidence == 'high':
        return 'accept'

    if review_suggestions:
        return 'review'

    if not parser_rows and has_usable_legacy_diagnostics:
        return 'review'

    if dominant_issue == 'missing_parser_rows':
        return 'manual_entry'

    return 'review'
