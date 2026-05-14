from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .contracts import (
    DiagnosticBundle,
    EngineProcessingState,
    ParserRow,
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

POC_SIGNAL_KEYS = [
    'detected_rows',
    'line_type_counts',
    'product_block',
    'product_block_rescue_diagnostics',
    'line_diagnostics',
    'processing_report',
]


class ReceiptIngestionPipeline:
    """
    Central orchestration wrapper around the current receipt_csv_poc outputs.

    IMPORTANT SSOT RULE:
    - this engine NEVER determines receipt category/status;
    - po_norm_status_label may only be passed through from upstream status services;
    - engine_processing_state is TECHNICAL ONLY and may never be used for UI counts/categories.
    """

    def ingest_json_payload(self, payload: Dict[str, Any]) -> ReceiptIngestionResult:
        metadata = payload.get('metadata', {}) or {}
        source_file = str(metadata.get('source_file') or payload.get('source_file') or 'unknown_receipt')
        receipt_id = Path(source_file).stem

        parser_rows = self._build_parser_rows(payload)
        review_suggestions = self._build_review_suggestions(payload)
        diagnostics = self._collect_diagnostics(metadata)
        processing_state = self._derive_engine_processing_state(payload)

        return ReceiptIngestionResult(
            receipt_id=receipt_id,
            source_file=source_file,
            parser_rows=parser_rows,
            review_suggestions=review_suggestions,
            diagnostics=DiagnosticBundle(diagnostics=diagnostics),
            engine_processing_state=processing_state,
            po_norm_status_label=metadata.get('po_norm_status_label'),
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
        source_rows = payload.get('rows', []) or payload.get('parser_rows', []) or []
        for row in source_rows:
            product_name = str(row.get('product_name') or row.get('item_text') or '').strip()
            if not product_name:
                continue
            rows.append(
                ParserRow(
                    product_name=product_name,
                    amount=_safe_float(row.get('line_total') or row.get('amount')),
                    quantity=_optional_float(row.get('quantity')),
                    unit_price=_optional_float(row.get('unit_price')),
                    line_no=row.get('line_no') or row.get('line_number'),
                    source='parser',
                    confidence=_optional_float(row.get('confidence')),
                    warning=str(row.get('warning') or ''),
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

    def _derive_engine_processing_state(
        self,
        payload: Dict[str, Any],
    ) -> EngineProcessingState:
        parser_rows = payload.get('rows', []) or payload.get('parser_rows', []) or []
        if parser_rows:
            return EngineProcessingState.PARSED

        metadata = payload.get('metadata', {}) or {}
        has_known_diagnostics = any(key in metadata for key in DIAGNOSTIC_KEYS)
        has_poc_signals = any(key in metadata for key in POC_SIGNAL_KEYS)
        has_schema_version = bool(payload.get('schema_version'))
        has_source_file = bool(metadata.get('source_file') or payload.get('source_file'))
        has_line_type_counts = bool(metadata.get('line_type_counts'))
        has_detected_rows_signal = 'detected_rows' in metadata

        if has_known_diagnostics or has_poc_signals or has_line_type_counts or has_detected_rows_signal:
            return EngineProcessingState.DIAGNOSTICS_AVAILABLE

        if has_schema_version and has_source_file:
            return EngineProcessingState.DIAGNOSTICS_AVAILABLE

        return EngineProcessingState.FAILED


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
