from __future__ import annotations

from typing import Any, Dict, Iterable, List


_EMPTY_NORMALIZED_REVIEW_DIAGNOSTICS = {
    'ocr_issues': [],
    'image_issues': [],
    'preprocessing_recommendations': [],
    'consensus_groups': [],
    'parser_safety_notes': [],
    'review_tasks': [],
}


def build_normalized_review_diagnostics(result: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize ingestion diagnostics for a future read-only review screen.

    This output is diagnostic-only. It does not calculate receipt categories,
    does not mutate parser rows, does not create inventory data, and does not
    promote shadow reconstruction candidates into parser output.
    """
    diagnostics = _as_dict(result.get('diagnostics'))
    summary = _as_dict(diagnostics.get('diagnostics_summary'))
    explainability = _as_dict(result.get('explainability'))
    parser_rows = _as_list(result.get('parser_rows'))
    review_suggestions = _as_list(result.get('review_suggestions'))

    normalized = _empty_contract()
    normalized['ocr_issues'] = _normalize_ocr_issues(diagnostics, summary, parser_rows)
    normalized['image_issues'] = _normalize_image_issues(diagnostics, summary)
    normalized['preprocessing_recommendations'] = _normalize_preprocessing_recommendations(diagnostics, summary)
    normalized['consensus_groups'] = _normalize_consensus_groups(diagnostics, review_suggestions)
    normalized['parser_safety_notes'] = _normalize_parser_safety_notes(diagnostics, summary, parser_rows, review_suggestions)
    normalized['review_tasks'] = _normalize_review_tasks(
        summary=summary,
        explainability=explainability,
        parser_rows=parser_rows,
        review_suggestions=review_suggestions,
    )
    return normalized


def _empty_contract() -> Dict[str, List[Dict[str, Any]]]:
    return {key: list(value) for key, value in _EMPTY_NORMALIZED_REVIEW_DIAGNOSTICS.items()}


def _normalize_ocr_issues(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
    parser_rows: List[Any],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    ocr_quality = str(summary.get('ocr_quality') or 'unknown')
    if ocr_quality in {'poor', 'moderate', 'unknown'}:
        issues.append(
            _issue(
                code='ocr_quality_limited',
                severity='medium' if ocr_quality == 'moderate' else 'high',
                title='OCR-kwaliteit beperkt',
                description=f'De OCR-kwaliteit is {ocr_quality}. Controleer of tekstregels juist zijn herkend.',
                source='diagnostics_summary',
            )
        )

    if not parser_rows:
        issues.append(
            _issue(
                code='no_parser_rows',
                severity='high',
                title='Geen veilige parserregels',
                description='Er zijn geen parserregels beschikbaar die automatisch verwerkt mogen worden.',
                source='receipt_ingestion_result',
            )
        )

    normalization = _as_dict(diagnostics.get('ocr_structural_normalization'))
    rejected_groups = _as_list(normalization.get('rejected_groups'))
    if rejected_groups:
        issues.append(
            _issue(
                code='ocr_rejected_line_groups',
                severity='medium',
                title='OCR-regelgroepen afgewezen',
                description=f'{len(rejected_groups)} OCR-regelgroep(en) zijn afgewezen door structurele normalisatie.',
                source='ocr_structural_normalization',
            )
        )

    return issues


def _normalize_image_issues(diagnostics: Dict[str, Any], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    image_quality = str(summary.get('image_quality') or 'unknown')
    if image_quality in {'poor', 'unknown'}:
        issues.append(
            _issue(
                code='image_quality_uncertain',
                severity='high' if image_quality == 'poor' else 'medium',
                title='Beeldkwaliteit onvoldoende of onbekend',
                description='Controleer scherpte, licht, schaduw en uitsnede van de kassabonfoto.',
                source='diagnostics_summary',
            )
        )

    governance = _as_dict(diagnostics.get('pre_ocr_image_correction_governance'))
    findings = _as_dict(governance.get('image_quality_findings'))
    shadow_risk = str(findings.get('shadow_risk') or '')
    if shadow_risk in {'medium', 'high'}:
        issues.append(
            _issue(
                code='shadow_risk_detected',
                severity='high' if shadow_risk == 'high' else 'medium',
                title='Schaduwriskico gevonden',
                description=f'De preprocessing-diagnose ziet {shadow_risk} schaduwriskico.',
                source='pre_ocr_image_correction_governance',
            )
        )

    return issues


def _normalize_preprocessing_recommendations(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    image_quality = str(summary.get('image_quality') or 'unknown')
    dominant_issue = str(summary.get('dominant_issue') or '')

    if image_quality == 'poor':
        recommendations.append(
            _recommendation(
                code='rescan_receipt',
                priority='high',
                title='Bon opnieuw fotograferen of scannen',
                description='Maak een scherpere foto met volledige bon, rechte uitsnede en minder schaduw.',
                source='diagnostics_summary',
            )
        )
    elif dominant_issue in {'ocr_structure', 'image_quality'}:
        recommendations.append(
            _recommendation(
                code='review_preprocessing_variants',
                priority='medium',
                title='Preprocessingvarianten controleren',
                description='Controleer welke preprocessingroute de beste OCR-structuur geeft.',
                source='diagnostics_summary',
            )
        )

    for key in (
        'adaptive_preprocessing_simulation',
        'zone_aware_preprocessing_diagnostics',
        'preprocessing_sequence_diagnostics',
    ):
        block = _as_dict(diagnostics.get(key))
        if block:
            recommendations.append(
                _recommendation(
                    code=f'{key}_available',
                    priority='medium',
                    title='Preprocessingdiagnose beschikbaar',
                    description=f'Diagnoseblok {key} is beschikbaar voor review.',
                    source=key,
                    details={'available_keys': sorted(str(k) for k in block.keys())[:12]},
                )
            )

    return recommendations


def _normalize_consensus_groups(
    diagnostics: Dict[str, Any],
    review_suggestions: List[Any],
) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    consensus = _as_dict(diagnostics.get('cross_route_ocr_consensus'))
    if consensus:
        groups.append(
            {
                'code': 'cross_route_ocr_consensus_available',
                'title': 'OCR-consensus beschikbaar',
                'description': 'Er zijn OCR-consensussignalen beschikbaar om regels handmatig te beoordelen.',
                'source': 'cross_route_ocr_consensus',
                'details': {'available_keys': sorted(str(k) for k in consensus.keys())[:12]},
            }
        )

    weighted = _as_dict(diagnostics.get('consensus_weighted_shadow_reconstruction'))
    weighted_rows = _as_list(weighted.get('weighted_rows'))
    if weighted or review_suggestions:
        groups.append(
            {
                'code': 'weighted_shadow_candidates',
                'title': 'Gewogen shadow-kandidaten',
                'description': 'Kandidaten zijn alleen bedoeld als reviewsignaal en worden niet automatisch parserregels.',
                'source': 'consensus_weighted_shadow_reconstruction',
                'candidate_count': len(weighted_rows),
                'review_suggestion_count': len(review_suggestions),
            }
        )

    return groups


def _normalize_parser_safety_notes(
    diagnostics: Dict[str, Any],
    summary: Dict[str, Any],
    parser_rows: List[Any],
    review_suggestions: List[Any],
) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    notes.append(
        {
            'code': 'diagnostic_only',
            'severity': 'info',
            'title': 'Alleen diagnose',
            'description': 'Diagnostics worden niet gebruikt om parserregels, voorraadmutaties of kassabonstatus te maken.',
            'source': 'receipt_ingestion_contract',
        }
    )

    if not parser_rows:
        notes.append(
            {
                'code': 'parser_output_not_available',
                'severity': 'high',
                'title': 'Geen automatische verwerking',
                'description': 'Zonder parserregels blijft menselijke review of handmatige invoer nodig.',
                'source': 'receipt_ingestion_result',
            }
        )

    if review_suggestions:
        notes.append(
            {
                'code': 'suggestions_require_human_review',
                'severity': 'medium',
                'title': 'Reviewsuggesties vereisen controle',
                'description': f'{len(review_suggestions)} suggestie(s) mogen alleen door een gebruiker worden beoordeeld.',
                'source': 'review_suggestions',
            }
        )

    safety = _as_dict(diagnostics.get('parser_safety_gating'))
    if safety:
        notes.append(
            {
                'code': 'parser_safety_gating_available',
                'severity': 'info',
                'title': 'Parser-safetydiagnose beschikbaar',
                'description': 'Parser-safety gating is beschikbaar als uitleglaag.',
                'source': 'parser_safety_gating',
                'details': {'available_keys': sorted(str(k) for k in safety.keys())[:12]},
            }
        )

    return notes


def _normalize_review_tasks(
    *,
    summary: Dict[str, Any],
    explainability: Dict[str, Any],
    parser_rows: List[Any],
    review_suggestions: List[Any],
) -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    action = str(explainability.get('recommended_user_action') or summary.get('recommended_user_action') or 'review')

    if action == 'rescan':
        tasks.append(
            _task(
                code='rescan_or_upload_better_image',
                priority='high',
                title='Maak een betere bonfoto',
                description='Upload een scherpere foto voordat inhoudelijke artikelreview zinvol is.',
            )
        )
    elif action == 'manual_entry':
        tasks.append(
            _task(
                code='enter_receipt_manually',
                priority='high',
                title='Voer bon handmatig in',
                description='Er zijn te weinig betrouwbare signalen om automatisch of via review te verwerken.',
            )
        )
    else:
        tasks.append(
            _task(
                code='review_detected_receipt_structure',
                priority='medium',
                title='Controleer OCR-structuur',
                description='Controleer winkelnaam, totaalbedrag en artikelregels voordat verwerking wordt overwogen.',
            )
        )

    if not parser_rows:
        tasks.append(
            _task(
                code='confirm_no_parser_rows',
                priority='medium',
                title='Bevestig dat automatische parseroutput ontbreekt',
                description='Er zijn geen parserregels beschikbaar; diagnostics mogen niet automatisch worden gepromoveerd.',
            )
        )

    if review_suggestions:
        tasks.append(
            _task(
                code='inspect_review_suggestions',
                priority='medium',
                title='Controleer reviewsuggesties',
                description='Bekijk de diagnostische suggesties handmatig voordat verdere verwerking plaatsvindt.',
            )
        )

    return tasks


def _issue(*, code: str, severity: str, title: str, description: str, source: str) -> Dict[str, Any]:
    return {
        'code': code,
        'severity': severity,
        'title': title,
        'description': description,
        'source': source,
    }


def _recommendation(
    *,
    code: str,
    priority: str,
    title: str,
    description: str,
    source: str,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    item = {
        'code': code,
        'priority': priority,
        'title': title,
        'description': description,
        'source': source,
    }
    if details:
        item['details'] = details
    return item


def _task(*, code: str, priority: str, title: str, description: str) -> Dict[str, Any]:
    return {
        'code': code,
        'priority': priority,
        'title': title,
        'description': description,
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
        return list(value)
    return []
