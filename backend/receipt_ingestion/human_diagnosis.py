from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


PRIMARY_ISSUES = {
    'poor_image_quality',
    'ocr_line_structure_unclear',
    'missing_total_amount',
    'missing_product_lines',
    'conflicting_ocr_routes',
    'missing_receipt_identity',
    'parser_output_not_safe',
    'insufficient_diagnostics',
}


def build_human_diagnosis(result: Dict[str, Any]) -> Dict[str, Any]:
    """Translate diagnostics into one human-centered, diagnostic-only diagnosis.

    This function never creates parser rows, never mutates inventory, and never
    determines a production receipt status. It only explains what a human should
    inspect next.
    """
    diagnostics = _as_dict(result.get('diagnostics'))
    summary = _as_dict(diagnostics.get('diagnostics_summary'))
    normalized = _as_dict(result.get('normalized_review_diagnostics'))
    explainability = _as_dict(result.get('explainability'))
    parser_rows = _as_list(result.get('parser_rows'))
    review_suggestions = _as_list(result.get('review_suggestions'))

    receipt_id = str(result.get('receipt_id') or '').strip()
    source_file = str(result.get('source_file') or '').strip()
    action = str(explainability.get('recommended_user_action') or summary.get('recommended_user_action') or '').strip()

    if _is_missing_identity(receipt_id, source_file):
        return _diagnosis(
            primary_issue='missing_receipt_identity',
            severity='high',
            admin_explanation='De bon kan niet betrouwbaar worden herkend. De bronnaam of bonidentiteit ontbreekt.',
            recommended_human_action='Controleer of dit een echte actieve kassabon is en upload de bon opnieuw als de bron ontbreekt.',
            evidence=['receipt_id/source_file ontbreekt of is unknown_receipt'],
        )

    if action == 'rescan' or summary.get('image_quality') == 'poor':
        return _diagnosis(
            primary_issue='poor_image_quality',
            severity='high',
            admin_explanation='De foto of scan is waarschijnlijk te slecht voor betrouwbare OCR.',
            recommended_human_action='Maak een nieuwe foto met volledige bon, rechte uitsnede, goed licht en zonder schaduw.',
            evidence=_evidence_from_image(summary, normalized),
        )

    if action == 'manual_entry' and not parser_rows:
        return _diagnosis(
            primary_issue='insufficient_diagnostics',
            severity='high',
            admin_explanation='Er zijn te weinig betrouwbare OCR- of diagnosesignalen om deze bon zinvol te controleren.',
            recommended_human_action='Voer de bon handmatig in of upload een duidelijkere bronbon.',
            evidence=['geen parserregels beschikbaar', 'advies is handmatige invoer'],
        )

    if _has_conflicting_ocr_routes(diagnostics):
        return _diagnosis(
            primary_issue='conflicting_ocr_routes',
            severity='medium',
            admin_explanation='Verschillende OCR-routes lijken elkaar tegen te spreken.',
            recommended_human_action='Vergelijk de herkende tekstregels en controleer vooral totalen en artikelregels handmatig.',
            evidence=['cross-route OCR consensus bevat conflictsignalen'],
        )

    if _total_amount_likely_missing(diagnostics, summary):
        return _diagnosis(
            primary_issue='missing_total_amount',
            severity='medium',
            admin_explanation='Het totaalbedrag is niet betrouwbaar uit de bon gehaald.',
            recommended_human_action='Controleer het totaalbedrag op de bon voordat verdere verwerking wordt overwogen.',
            evidence=['dominant issue of diagnostics wijst op ontbrekend of onduidelijk totaal'],
        )

    if _product_lines_likely_missing(result, normalized, parser_rows, review_suggestions):
        return _diagnosis(
            primary_issue='missing_product_lines',
            severity='medium',
            admin_explanation='Artikelregels zijn niet betrouwbaar genoeg herkend als veilige parseroutput.',
            recommended_human_action='Controleer of de artikelregels zichtbaar en volledig zijn; vul ontbrekende regels handmatig aan.',
            evidence=['geen parserregels beschikbaar', f'{len(review_suggestions)} diagnostische suggesties'],
        )

    if _parser_output_not_safe(normalized, parser_rows):
        return _diagnosis(
            primary_issue='parser_output_not_safe',
            severity='medium',
            admin_explanation='De parseroutput is nog niet veilig genoeg om automatisch te gebruiken.',
            recommended_human_action='Controleer de voorgestelde regels handmatig; laat Rezzerv niets automatisch verwerken.',
            evidence=['parser-safety notities aanwezig', 'diagnostic-only verwerking'],
        )

    if _ocr_structure_unclear(summary, normalized):
        return _diagnosis(
            primary_issue='ocr_line_structure_unclear',
            severity='medium',
            admin_explanation='De OCR-tekstregels zijn nog onvoldoende duidelijk gescheiden.',
            recommended_human_action='Controleer de artikelregels, subtotalen en totaalregel handmatig.',
            evidence=['OCR-kwaliteit of lijnstructuur is beperkt'],
        )

    return _diagnosis(
        primary_issue='insufficient_diagnostics',
        severity='medium',
        admin_explanation='De diagnose is nog te algemeen om een specifieke oorzaak te noemen.',
        recommended_human_action='Controleer de bon handmatig en gebruik technische details alleen voor analyse door het scrumteam.',
        evidence=['fallbackdiagnose: geen specifieker probleemtype gevonden'],
    )


def _diagnosis(
    *,
    primary_issue: str,
    severity: str,
    admin_explanation: str,
    recommended_human_action: str,
    evidence: List[str],
) -> Dict[str, Any]:
    if primary_issue not in PRIMARY_ISSUES:
        primary_issue = 'insufficient_diagnostics'
    if severity not in {'low', 'medium', 'high'}:
        severity = 'medium'
    return {
        'primary_issue': primary_issue,
        'severity': severity,
        'admin_explanation': admin_explanation,
        'recommended_human_action': recommended_human_action,
        'evidence': [str(item) for item in evidence if str(item or '').strip()],
        'diagnostic_only': True,
    }


def _is_missing_identity(receipt_id: str, source_file: str) -> bool:
    values = {receipt_id.strip().lower(), source_file.strip().lower(), Path(source_file).stem.strip().lower()}
    return not receipt_id or not source_file or 'unknown_receipt' in values or 'unknown' in values


def _evidence_from_image(summary: Dict[str, Any], normalized: Dict[str, Any]) -> List[str]:
    evidence = [f"image_quality={summary.get('image_quality') or 'unknown'}"]
    image_issues = _as_list(normalized.get('image_issues'))
    for issue in image_issues[:2]:
        if isinstance(issue, dict):
            evidence.append(str(issue.get('title') or issue.get('code') or 'beeldprobleem'))
    return evidence


def _has_conflicting_ocr_routes(diagnostics: Dict[str, Any]) -> bool:
    consensus = _as_dict(diagnostics.get('cross_route_ocr_consensus'))
    text = str(consensus).lower()
    return any(token in text for token in ('conflict', 'disagree', 'mismatch', 'divergent', 'tegenstrijd'))


def _total_amount_likely_missing(diagnostics: Dict[str, Any], summary: Dict[str, Any]) -> bool:
    dominant = str(summary.get('dominant_issue') or '').lower()
    if 'total' in dominant or 'totaal' in dominant:
        return True
    text = str(diagnostics).lower()
    return any(token in text for token in ('missing_total', 'total_not_found', 'totaal ontbreekt', 'total amount'))


def _product_lines_likely_missing(
    result: Dict[str, Any],
    normalized: Dict[str, Any],
    parser_rows: List[Any],
    review_suggestions: List[Any],
) -> bool:
    if parser_rows:
        return False
    receipt_id = str(result.get('receipt_id') or '').strip().lower()
    if receipt_id and receipt_id != 'unknown_receipt':
        return True
    ocr_issues = _as_list(normalized.get('ocr_issues'))
    return bool(ocr_issues or review_suggestions)


def _parser_output_not_safe(normalized: Dict[str, Any], parser_rows: List[Any]) -> bool:
    if parser_rows:
        return False
    safety_notes = _as_list(normalized.get('parser_safety_notes'))
    text = str(safety_notes).lower()
    return bool(safety_notes) and any(token in text for token in ('geen automatische verwerking', 'diagnostic', 'parser'))


def _ocr_structure_unclear(summary: Dict[str, Any], normalized: Dict[str, Any]) -> bool:
    dominant = str(summary.get('dominant_issue') or '').lower()
    ocr_quality = str(summary.get('ocr_quality') or '').lower()
    return 'ocr' in dominant or ocr_quality in {'poor', 'moderate', 'unknown'} or bool(_as_list(normalized.get('ocr_issues')))


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []
