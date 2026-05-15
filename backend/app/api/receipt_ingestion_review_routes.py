from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

try:
    from receipt_ingestion import ReceiptIngestionPipeline
    from receipt_ingestion.explainability import build_receipt_explainability
    from receipt_ingestion.normalized_review_diagnostics import build_normalized_review_diagnostics
except ModuleNotFoundError:  # local repo-root CLI/import compatibility
    from backend.receipt_ingestion import ReceiptIngestionPipeline
    from backend.receipt_ingestion.explainability import build_receipt_explainability
    from backend.receipt_ingestion.normalized_review_diagnostics import build_normalized_review_diagnostics

router = APIRouter(
    prefix='/api/receipt-ingestion',
    tags=['receipt-ingestion-review-preview'],
)

_pipeline_factory: Callable[[], ReceiptIngestionPipeline] | None = None
_allowed_test_runs_root: Path | None = None

READINESS_LABELS = {
    'candidate_for_controlled_parser_augmentation',
    'review_only',
    'rescan_needed',
    'manual_entry_needed',
    'insufficient_diagnostics',
}

ARCHIVE_PATH_MARKERS = {'archived', 'archive', 'gearchiveerd', 'verwijderd', 'deleted'}
ARCHIVE_STATUS_VALUES = {'archived', 'archive', 'gearchiveerd', 'deleted', 'removed', 'verwijderd'}
ARCHIVE_BOOLEAN_KEYS = {'is_archived', 'archived', 'is_deleted', 'deleted', 'functionally_deleted'}
ARCHIVE_TIMESTAMP_KEYS = {'archived_at', 'deleted_at', 'removed_at'}


def configure_receipt_ingestion_review_routes(
    *,
    pipeline_factory: Callable[[], ReceiptIngestionPipeline] | None = None,
    allowed_test_runs_root: Path | None = None,
) -> None:
    """Configure read-only review-preview dependencies.

    This router is intentionally preview-only:
    - no database writes;
    - no UI coupling;
    - no parser replacement;
    - no receipt status calculation.
    """
    global _pipeline_factory, _allowed_test_runs_root
    _pipeline_factory = pipeline_factory or ReceiptIngestionPipeline
    _allowed_test_runs_root = Path(allowed_test_runs_root or Path('tools') / 'receipt_csv_poc' / 'test_runs')


def _require_configured() -> tuple[Callable[[], ReceiptIngestionPipeline], Path]:
    if _pipeline_factory is None or _allowed_test_runs_root is None:
        configure_receipt_ingestion_review_routes()
    assert _pipeline_factory is not None
    assert _allowed_test_runs_root is not None
    return _pipeline_factory, _allowed_test_runs_root


def _allowed_root_abs(allowed_root: Path) -> Path:
    return (Path.cwd() / allowed_root).resolve() if not allowed_root.is_absolute() else allowed_root.resolve()


def _resolve_safe_json_path(json_path: str, allowed_root: Path) -> Path:
    raw_path = Path(json_path)
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
    else:
        candidate = (Path.cwd() / raw_path).resolve()

    allowed = _allowed_root_abs(allowed_root)

    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail='JSON-pad ligt buiten toegestane receipt_csv_poc/test_runs map') from exc

    if candidate.suffix.lower() != '.json':
        raise HTTPException(status_code=400, detail='Alleen JSON-bestanden zijn toegestaan')

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail='POC JSON-bestand niet gevonden')

    return candidate


def _public_json_path(path: Path, allowed_root: Path) -> str:
    allowed_abs = _allowed_root_abs(allowed_root)
    relative_to_allowed = path.resolve().relative_to(allowed_abs).as_posix()
    root_label = allowed_root.as_posix() if not allowed_root.is_absolute() else 'tools/receipt_csv_poc/test_runs'
    return f'{root_label.rstrip("/")}/{relative_to_allowed}'


def _iter_safe_json_files(allowed_root: Path, *, include_archived: bool = False):
    allowed_abs = _allowed_root_abs(allowed_root)
    if not allowed_abs.exists() or not allowed_abs.is_dir():
        return []

    files = []
    for json_file in sorted(allowed_abs.glob('**/*.json')):
        if not json_file.is_file():
            continue
        try:
            json_file.resolve().relative_to(allowed_abs)
        except ValueError:
            continue
        if not include_archived and _is_archived_receipt_json(json_file, allowed_abs):
            continue
        files.append(json_file)
    return files


def _deduplicate_receipt_json_files(json_files: list[Path]) -> list[Path]:
    """Keep one current diagnostic JSON per functional receipt.

    POC test_runs contain the same receipt repeated over many diagnostic runs.
    The admin cockpit must show functional receipts, not every historical run.
    """
    chosen: dict[str, Path] = {}
    for json_file in json_files:
        key = _receipt_identity_key(json_file)
        current = chosen.get(key)
        if current is None or _json_file_sort_key(json_file) > _json_file_sort_key(current):
            chosen[key] = json_file
    return sorted(chosen.values(), key=lambda path: _receipt_identity_key(path))


def _receipt_identity_key(json_file: Path) -> str:
    try:
        payload = json.loads(json_file.read_text(encoding='utf-8'))
    except Exception:
        return json_file.stem.strip().lower()

    if not isinstance(payload, dict):
        return json_file.stem.strip().lower()

    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    source_file = str(metadata.get('source_file') or payload.get('source_file') or '').strip().lower()
    if source_file:
        return Path(source_file).stem.strip().lower()
    return json_file.stem.strip().lower()


def _json_file_sort_key(json_file: Path) -> tuple[float, str]:
    try:
        mtime = json_file.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (mtime, json_file.as_posix())


def _is_archived_receipt_json(json_file: Path, allowed_abs: Path) -> bool:
    try:
        relative_parts = [part.lower() for part in json_file.resolve().relative_to(allowed_abs).parts]
    except ValueError:
        relative_parts = [part.lower() for part in json_file.parts]

    if any(part in ARCHIVE_PATH_MARKERS for part in relative_parts):
        return True

    try:
        payload = json.loads(json_file.read_text(encoding='utf-8'))
    except Exception:
        return False

    if not isinstance(payload, dict):
        return False

    metadata = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {}
    candidates = [payload, metadata]

    for source in candidates:
        for key in ARCHIVE_BOOLEAN_KEYS:
            if source.get(key) is True:
                return True
        for key in ARCHIVE_TIMESTAMP_KEYS:
            if source.get(key):
                return True
        status_value = str(source.get('status') or source.get('receipt_status') or source.get('archive_status') or '').strip().lower()
        if status_value in ARCHIVE_STATUS_VALUES:
            return True

    return False


def _build_response_payload(result) -> dict:
    payload = result.to_dict()
    payload['explainability'] = build_receipt_explainability(payload)
    payload['normalized_review_diagnostics'] = build_normalized_review_diagnostics(payload)
    return payload


def _derive_readiness_label(payload: dict) -> str:
    explainability = payload.get('explainability') or {}
    normalized = payload.get('normalized_review_diagnostics') or {}
    summary = (payload.get('diagnostics') or {}).get('diagnostics_summary') or {}

    action = str(explainability.get('recommended_user_action') or summary.get('recommended_user_action') or '').strip()
    has_legacy_diag = bool(summary.get('has_usable_legacy_poc_diagnostics'))
    parser_rows = payload.get('parser_rows') or []
    review_suggestions = payload.get('review_suggestions') or []
    ocr_issues = normalized.get('ocr_issues') or []
    image_issues = normalized.get('image_issues') or []
    review_tasks = normalized.get('review_tasks') or []
    safety_notes = normalized.get('parser_safety_notes') or []

    if action == 'rescan':
        return 'rescan_needed'
    if action == 'manual_entry':
        return 'manual_entry_needed'
    if not has_legacy_diag and not parser_rows and not review_suggestions:
        return 'insufficient_diagnostics'
    if parser_rows and action == 'accept':
        return 'candidate_for_controlled_parser_augmentation'
    if review_suggestions and not image_issues:
        return 'candidate_for_controlled_parser_augmentation'
    if has_legacy_diag and (ocr_issues or review_tasks or safety_notes):
        return 'review_only'
    return 'insufficient_diagnostics'


def _build_readiness_item(*, json_file: Path, allowed_root: Path, pipeline: ReceiptIngestionPipeline) -> dict:
    public_path = _public_json_path(json_file, allowed_root)
    try:
        result = pipeline.ingest_json_file(json_file)
        payload = _build_response_payload(result)
        normalized = payload.get('normalized_review_diagnostics') or {}
        explainability = payload.get('explainability') or {}
        summary = (payload.get('diagnostics') or {}).get('diagnostics_summary') or {}
        readiness = _derive_readiness_label(payload)
        if readiness not in READINESS_LABELS:
            readiness = 'insufficient_diagnostics'
        return {
            'json_path': public_path,
            'file_name': json_file.name,
            'receipt_id': payload.get('receipt_id') or json_file.stem,
            'source_file': payload.get('source_file') or '-',
            'engine_processing_state': payload.get('engine_processing_state') or 'failed',
            'recommended_user_action': explainability.get('recommended_user_action') or summary.get('recommended_user_action') or '-',
            'main_reason': explainability.get('main_reason') or summary.get('dominant_issue') or '-',
            'ocr_issue_count': len(normalized.get('ocr_issues') or []),
            'image_issue_count': len(normalized.get('image_issues') or []),
            'review_task_count': len(normalized.get('review_tasks') or []),
            'readiness': readiness,
            'readiness_is_diagnostic_only': True,
        }
    except json.JSONDecodeError:
        return _failed_readiness_item(public_path, json_file, 'manual_entry_needed', 'invalid_json')
    except Exception:
        return _failed_readiness_item(public_path, json_file, 'insufficient_diagnostics', 'readiness_build_failed')


def _failed_readiness_item(public_path: str, json_file: Path, readiness: str, reason: str) -> dict:
    return {
        'json_path': public_path,
        'file_name': json_file.name,
        'receipt_id': json_file.stem,
        'source_file': '-',
        'engine_processing_state': 'failed',
        'recommended_user_action': 'manual_entry' if readiness == 'manual_entry_needed' else '-',
        'main_reason': reason,
        'ocr_issue_count': 0,
        'image_issue_count': 0,
        'review_task_count': 0,
        'readiness': readiness,
        'readiness_is_diagnostic_only': True,
    }


@router.get('/test-run-jsons')
def get_receipt_ingestion_test_run_jsons():
    _pipeline_factory, allowed_root = _require_configured()
    source_files = _iter_safe_json_files(allowed_root)
    active_files = _deduplicate_receipt_json_files(source_files)
    items = []
    for json_file in active_files:
        run_name = '-'
        parts = json_file.resolve().relative_to(_allowed_root_abs(allowed_root)).parts
        if parts:
            run_name = parts[0]
        items.append(
            {
                'json_path': _public_json_path(json_file, allowed_root),
                'file_name': json_file.name,
                'run_name': run_name,
            }
        )

    return {
        'items': items,
        'count': len(items),
        'source_count': len(source_files),
        'archived_receipts_excluded': True,
        'duplicate_runs_collapsed': True,
    }


@router.get('/review-readiness-baseline')
def get_receipt_ingestion_review_readiness_baseline():
    pipeline_factory, allowed_root = _require_configured()
    pipeline = pipeline_factory()
    source_files = _iter_safe_json_files(allowed_root)
    active_files = _deduplicate_receipt_json_files(source_files)
    items = [
        _build_readiness_item(json_file=json_file, allowed_root=allowed_root, pipeline=pipeline)
        for json_file in active_files
    ]
    return {
        'items': items,
        'count': len(items),
        'source_count': len(source_files),
        'readiness_labels': sorted(READINESS_LABELS),
        'diagnostic_only': True,
        'archived_receipts_excluded': True,
        'duplicate_runs_collapsed': True,
    }


@router.get('/review-preview')
def get_receipt_ingestion_review_preview(
    json_path: str = Query(..., description='Pad naar POC JSON onder tools/receipt_csv_poc/test_runs'),
):
    pipeline_factory, allowed_root = _require_configured()
    safe_path = _resolve_safe_json_path(json_path, allowed_root)

    try:
        pipeline = pipeline_factory()
        result = pipeline.ingest_json_file(safe_path)
        return result.to_dict()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='POC JSON-bestand is ongeldig') from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Receipt ingestion preview kon niet worden opgebouwd') from exc


@router.get('/explainability-preview')
def get_receipt_ingestion_explainability_preview(
    json_path: str = Query(..., description='Pad naar POC JSON onder tools/receipt_csv_poc/test_runs'),
):
    pipeline_factory, allowed_root = _require_configured()
    safe_path = _resolve_safe_json_path(json_path, allowed_root)

    try:
        pipeline = pipeline_factory()
        result = pipeline.ingest_json_file(safe_path)
        return _build_response_payload(result)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='POC JSON-bestand is ongeldig') from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail='Receipt ingestion explainability preview kon niet worden opgebouwd') from exc
