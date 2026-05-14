from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .contracts import (
    DiagnosticBundle,
    ParserRow,
    QualityStatus,
    ReceiptIngestionResult,
    ReviewSuggestion,
)


DIAGNOSTIC_KEYS = [
    'quantity_merge_amount_diagnostics',
    'discount_netto_diagnostics',
    'ocr_structural_normalization',
    'document_isolation_enhancement_diagnostics',
    'adaptive_ocr_orchestration',
    'cross_route_ocr_consensus',
    'consensus_weighted_shadow_reconstruction',
    'simulated_parser_integration',
    'parser_safety_gating',
    'pre_ocr_image_correction_governance',
    'adaptive_preprocessing_simulation',
    'zone_aware_preprocessing_diagnostics',
    'cross_zone_interference_diagnostics',
    'preprocessing_sequence_diagnostics',
]


class ReceiptIngestionPipeline:
    """
    Central orchestration wrapper around the current receipt_csv_poc outputs.

    This is intentionally conservative:
    - no parser replacement;
    - no database integration;
    - no UI integration;
    - no shadow rows promoted to parser rows.
    """

    def ingest_json_payload(self, payload: Dict[str, Any]) -> ReceiptIngestionResult:
        metadata = payload.get('metadata', {}) or {}
        source_file = str(metadata.get('source_file') or payload.get('source_file') or 'unknown_receipt')
        receipt_id = Path(source_file).stem

        parser_rows = self._build_parser_rows(payload)
        review_suggestions = self._build_review_suggestions(payload)
        diagnostics = self._collect_diagnostics(metadata)
        quality_status = self._derive_quality_status(payload, review_suggestions)

        return ReceiptIngestionResult(
            receipt_id=receipt_id,
            source_file=source_file,
            parser_rows=parser_rows,
            review_suggestions=review_suggestions,
            diagnostics=DiagnosticBundle(diagnostics=diagnostics),
            quality_status=quality_status,
        )

    def ingest_json_file(self, path: Path) -> ReceiptIngestionResult:
        payload = json.loads(path.read_text(encoding='utf-8'))
        return self.ingest_json_payload(payload)

    def ingest_directory(self, directory: Path) -> List[ReceiptIngestionResult]:
        results: List[ReceiptIngestionResult] = []
        for json_file in sorted(directory.glob('*.json')):
            results.append(self.ingest_json_file(json_file))
        return results

    def _build_parser_rows(self, payload: Dict[str, Any]) -> List[ParserRow]:
        rows = []
        for row in payload.get('rows', []) or []:
            product_name = str(row.get('product_name') or '').strip()
            if not product_name:
                continue
            rows.append(
                ParserRow(
                    product_name=product_name,
                    amount=_safe_float(row.get('line_total')),
                    quantity=_optional_float(row.get('quantity')),
                    unit_price=_optional_float(row.get('unit_price')),
                    line_no=row.get('line_no'),
                    source='parser',
                    confidence=_optional_float(row.get('confidence')),
                    warning='',
                )
            )
        return rows

    def _build_review_suggestions(self, payload: Dict[str, Any]) -> List[ReviewSuggestion]:
        metadata = payload.get('metadata', {}) or {}
        weighted = metadata.get('consensus_weighted_shadow_reconstruction', {}) or {}
        suggestions: List[ReviewSuggestion] = []
        for row in weighted.get('weighted_rows', []) or []:
            risk_level = str(row.get('risk_level') or 'unknown')
            if risk_level not in {'low', 'medium'}:
                continue
            suggestions.append(
                ReviewSuggestion(
                    product_name=str(row.get('product_name') or '').strip(),
                    amount=_safe_float(row.get('amount')),
                    reason=str(row.get('weighting_reason') or 'consensus_weighted_shadow_candidate'),
                    risk_level=risk_level,
                    confidence=_optional_float(row.get('consensus_weighted_score')),
                    source='consensus_weighted_shadow_reconstruction',
                    diagnostics_ref='consensus_weighted_shadow_reconstruction.weighted_rows',
                )
            )
        return suggestions

    def _collect_diagnostics(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        collected = {}
        for key in DIAGNOSTIC_KEYS:
            if key in metadata:
                collected[key] = metadata[key]
        return collected

    def _derive_quality_status(
        self,
        payload: Dict[str, Any],
        review_suggestions: List[ReviewSuggestion],
    ) -> QualityStatus:
        metadata = payload.get('metadata', {}) or {}
        gating = metadata.get('parser_safety_gating', {}) or {}
        readiness = (gating.get('readiness') or {}).get('ready_for_controlled_integration')

        if readiness is True and not review_suggestions:
            return QualityStatus.CONTROLLED

        parser_rows = payload.get('rows', []) or []
        if not parser_rows:
            return QualityStatus.FAILED

        return QualityStatus.REVIEW_NEEDED


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == '':
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _optional_float(value: Any):
    try:
        if value is None or value == '':
            return None
        return float(value)
    except Exception:
        return None


def _write_results(results: Iterable[ReceiptIngestionResult], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serializable = [result.to_dict() for result in results]
    output.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description='Receipt ingestion engine orchestrator')
    parser.add_argument('--json', help='Single receipt json file')
    parser.add_argument('--json-dir', help='Directory with receipt json files')
    parser.add_argument('--output', default='receipt_ingestion_output.json')
    args = parser.parse_args()

    pipeline = ReceiptIngestionPipeline()

    if args.json:
        results = [pipeline.ingest_json_file(Path(args.json))]
    elif args.json_dir:
        results = pipeline.ingest_directory(Path(args.json_dir))
    else:
        raise SystemExit('Provide --json or --json-dir')

    _write_results(results, Path(args.output))
    print(f'[OK] Receipt ingestion results written to: {args.output}')


if __name__ == '__main__':
    main()
