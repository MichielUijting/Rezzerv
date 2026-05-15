from __future__ import annotations

from typing import Any, Dict, Iterable, List


Q_LABELS = {
    'cross_route_ocr_consensus': 'cross_route_ocr_consensus',
    'consensus_weighted_shadow_reconstruction': 'consensus_weighted_shadow_reconstruction',
    'parser_safety_gating': 'parser_safety_gating',
    'pre_ocr_image_correction_governance': 'pre_ocr_image_correction_governance',
    'adaptive_preprocessing_simulation': 'adaptive_preprocessing_simulation',
    'zone_aware_preprocessing_diagnostics': 'zone_aware_preprocessing_diagnostics',
    'cross_zone_interference_diagnostics': 'cross_zone_interference_diagnostics',
    'preprocessing_sequence_diagnostics': 'preprocessing_sequence_diagnostics',
    'ocr_structural_normalization': 'ocr_structural_normalization',
    'document_isolation_enhancement_diagnostics': 'document_isolation_enhancement_diagnostics',
}

ALLOWED_ACTIONS = {'accept', 'review', 'rescan', 'manual_entry'}


def build_receipt_explainability(result: Dict[str, Any]) -> Dict[str, Any]:
    """Build human-readable, review-oriented receipt ingestion explanations.

    This module is intentionally diagnostic-only. It does not mutate parser rows,
    does not promote diagnostic candidates, and does not determine receipt
    categories. Any production receipt category remains outside the ingestion
    engine.
    """
    diagnostics = _as_dict(result.get('diagnostics'))
    summary = _as_dict(diagnostics.get('diagnostics_summary'))
    parser_rows = _as_list(result.get('parser_rows'))
    suggestions = _as_list(result.get('review_suggestions'))

    action = _normalize_action(summary.get('recommended_user_action'), parser_rows)
    main_reason = _main_reason(summary, parser_rows, suggestions)

    return {
        'main_reason': main_reason,
        'ocr_findings': _build_ocr_findings(diagnostics, summary, parser_rows),
        'preprocessing_findings': _build_preprocessing_findings(diagnostics, summary),
        'consensus_findings': _build_consensus_findings(diagnostics, suggestions),
        'safety_findings': _build_safety_findings(diagnostics, summary, suggestions),
        'review_rationale': _build_review_rationale(
            summary=summary,
            parser_rows=parser_rows,
            suggestions=suggestions,
            recommended_user_action=action,
        ),
        'recommended_user_action': action,
    }


def _main_reason(summary: Dict[str, Any], parser_rows: List[Any], suggestions: List[Any]) -> str:
    dominant_issue = str(summary.get('dominant_issue') or '').strip()
    if dominant_issue and dominant_issue != 'none':
        return dominant_issue
    if parser_rows:
        return 'parser_rows_available'
    if suggestions:
        return 'diagnostic_review_candidates_available'
    return 'insufficient_receipt_signals'


def _build_ocr_findings(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
    parser_rows: List[Any],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    findings.append(
        {
            'source': 'diagnostics_summary',
            'finding': 'ocr_quality',
            'value': summary.get('ocr_quality') or 'unknown',
        }
    )

    normalization = _as_dict(diagnostics.get('ocr_structural_normalization'))
    normalized_groups = _as_list(normalization.get('normalized_line_groups'))
    rejected_groups = _as_list(normalization.get('rejected_groups'))
    if normalized_groups or rejected_groups:
        findings.append(
            {
                'source': Q_LABELS['ocr_structural_normalization'],
                'finding': 'line_group_structure',
                'normalized_group_count': len(normalized_groups),
                'rejected_group_count': len(rejected_groups),
            }
        )

    findings.append(
        {
            'source': 'receipt_ingestion_result',
            'finding': 'parser_rows_detected',
            'value': len(parser_rows),
        }
    )
    return findings


def _build_preprocessing_findings(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = [
        {
            'source': 'diagnostics_summary',
            'finding': 'image_quality',
            'value': summary.get('image_quality') or 'unknown',
        }
    ]

    for key in (
        'document_isolation_enhancement_diagnostics',
        'pre_ocr_image_correction_governance',
        'adaptive_preprocessing_simulation',
        'zone_aware_preprocessing_diagnostics',
        'cross_zone_interference_diagnostics',
        'preprocessing_sequence_diagnostics',
    ):
        block = _as_dict(diagnostics.get(key))
        if not block:
            continue
        findings.append(_compact_block_finding(source=Q_LABELS[key], block=block))

    return findings


def _build_consensus_findings(
    diagnostics: Dict[str, Any],
    suggestions: List[Any],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    consensus = _as_dict(diagnostics.get('cross_route_ocr_consensus'))
    if consensus:
        findings.append(_compact_block_finding(source=Q_LABELS['cross_route_ocr_consensus'], block=consensus))

    weighted = _as_dict(diagnostics.get('consensus_weighted_shadow_reconstruction'))
    weighted_rows = _as_list(weighted.get('weighted_rows'))
    if weighted:
        findings.append(
            {
                'source': Q_LABELS['consensus_weighted_shadow_reconstruction'],
                'finding': 'weighted_shadow_candidates',
                'candidate_count': len(weighted_rows),
                'review_suggestion_count': len(suggestions),
            }
        )

    return findings or [
        {
            'source': 'receipt_ingestion_result',
            'finding': 'consensus_signals',
            'value': 'not_available',
        }
    ]


def _build_safety_findings(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
    suggestions: List[Any],
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = [
        {
            'source': 'diagnostics_summary',
            'finding': 'safety_level',
            'value': summary.get('safety_level') or 'unknown',
        },
        {
            'source': 'receipt_ingestion_result',
            'finding': 'diagnostic_suggestion_count',
            'value': len(suggestions),
        },
    ]

    safety = _as_dict(diagnostics.get('parser_safety_gating'))
    if safety:
        findings.append(_compact_block_finding(source=Q_LABELS['parser_safety_gating'], block=safety))

    return findings


def _build_review_rationale(
    *,
    summary: Dict[str, Any],
    parser_rows: List[Any],
    suggestions: List[Any],
    recommended_user_action: str,
) -> List[str]:
    rationale: List[str] = []

    if recommended_user_action == 'accept':
        rationale.append('Parserregels zijn aanwezig en de parser-confidence is hoog.')
    elif recommended_user_action == 'rescan':
        rationale.append('De beeldkwaliteit is onvoldoende; opnieuw scannen of fotograferen is waarschijnlijk nodig.')
    elif recommended_user_action == 'manual_entry':
        rationale.append('Er zijn te weinig bruikbare OCR- of diagnosesignalen voor een zinvolle review.')
    else:
        rationale.append('Er is bruikbare diagnostiek aanwezig, maar onvoldoende veilige parseroutput voor automatische acceptatie.')

    dominant_issue = summary.get('dominant_issue')
    if dominant_issue and dominant_issue != 'none':
        rationale.append(f'Belangrijkste diagnosepunt: {dominant_issue}.')

    if not parser_rows:
        rationale.append('Er worden geen parserregels gepromoveerd vanuit diagnostics.')

    if suggestions:
        rationale.append(f'Er zijn {len(suggestions)} diagnostische reviewsuggesties beschikbaar voor menselijke controle.')

    return rationale


def _compact_block_finding(*, source: str, block: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'source': source,
        'finding': 'diagnostic_block_available',
        'keys': sorted(str(key) for key in block.keys())[:12],
    }


def _normalize_action(value: Any, parser_rows: List[Any]) -> str:
    action = str(value or 'review').strip()
    if action not in ALLOWED_ACTIONS:
        action = 'review'
    if not parser_rows and action == 'accept':
        return 'review'
    return action


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return list(value)
    return []
