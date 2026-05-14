from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

try:
    from receipt_ingestion import ReceiptIngestionPipeline
except ModuleNotFoundError:  # local repo-root CLI/import compatibility
    from backend.receipt_ingestion import ReceiptIngestionPipeline

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


def _resolve_safe_json_path(json_path: str, allowed_root: Path) -> Path:
    raw_path = Path(json_path)
    if raw_path.is_absolute():
        candidate = raw_path.resolve()
    else:
        candidate = (Path.cwd() / raw_path).resolve()

    allowed = (Path.cwd() / allowed_root).resolve() if not allowed_root.is_absolute() else allowed_root.resolve()

    try:
        candidate.relative_to(allowed)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail='JSON-pad ligt buiten toegestane receipt_csv_poc/test_runs map') from exc

    if candidate.suffix.lower() != '.json':
        raise HTTPException(status_code=400, detail='Alleen JSON-bestanden zijn toegestaan')

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail='POC JSON-bestand niet gevonden')

    return candidate


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
