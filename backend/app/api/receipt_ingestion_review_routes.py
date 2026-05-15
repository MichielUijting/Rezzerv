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


def _build_response_payload(result) -> dict:
    payload = result.to_dict()
    payload['explainability'] = build_receipt_explainability(payload)
    payload['normalized_review_diagnostics'] = build_normalized_review_diagnostics(payload)
    return payload


@router.get('/test-run-jsons')
def get_receipt_ingestion_test_run_jsons():
    _pipeline_factory, allowed_root = _require_configured()
    allowed_abs = _allowed_root_abs(allowed_root)
    if not allowed_abs.exists() or not allowed_abs.is_dir():
        return {'items': [], 'count': 0}

    items = []
    for json_file in sorted(allowed_abs.glob('**/*.json')):
        if not json_file.is_file():
            continue
        try:
            json_file.resolve().relative_to(allowed_abs)
        except ValueError:
            continue
        run_name = '-'
        parts = json_file.resolve().relative_to(allowed_abs).parts
        if parts:
            run_name = parts[0]
        items.append(
            {
                'json_path': _public_json_path(json_file, allowed_root),
                'file_name': json_file.name,
                'run_name': run_name,
            }
        )

    return {'items': items, 'count': len(items)}


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
