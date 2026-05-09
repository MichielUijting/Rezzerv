from __future__ import annotations

from typing import Callable, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/admin",
    tags=["receipt-admin"],
)

_engine = None
_backfill_purchase_import_live_aliases: Callable | None = None
_backfill_receipt_unpack_statuses: Callable | None = None
_validate_receipt_status_baseline: Callable | None = None
_diagnose_receipt_status_baseline: Callable | None = None


def configure_receipt_admin_routes(
    *,
    engine,
    backfill_purchase_import_live_aliases: Callable,
    backfill_receipt_unpack_statuses: Callable,
    validate_receipt_status_baseline: Callable,
    diagnose_receipt_status_baseline: Callable,
) -> None:
    """Configure admin route dependencies supplied by main.py.

    The admin router is intentionally dependency-injected to avoid importing
    app.main from this module. This keeps the extraction limited to routing
    structure and preserves the existing admin endpoint behaviour.
    """
    global _engine
    global _backfill_purchase_import_live_aliases
    global _backfill_receipt_unpack_statuses
    global _validate_receipt_status_baseline
    global _diagnose_receipt_status_baseline

    _engine = engine
    _backfill_purchase_import_live_aliases = backfill_purchase_import_live_aliases
    _backfill_receipt_unpack_statuses = backfill_receipt_unpack_statuses
    _validate_receipt_status_baseline = validate_receipt_status_baseline
    _diagnose_receipt_status_baseline = diagnose_receipt_status_baseline


def _require_configured() -> tuple[object, Callable, Callable, Callable, Callable]:
    if (
        _engine is None
        or _backfill_purchase_import_live_aliases is None
        or _backfill_receipt_unpack_statuses is None
        or _validate_receipt_status_baseline is None
        or _diagnose_receipt_status_baseline is None
    ):
        raise HTTPException(status_code=500, detail='Receipt admin router is niet geconfigureerd')
    return (
        _engine,
        _backfill_purchase_import_live_aliases,
        _backfill_receipt_unpack_statuses,
        _validate_receipt_status_baseline,
        _diagnose_receipt_status_baseline,
    )


@router.post("/backfill-purchase-import-live-aliases")
def run_purchase_import_live_alias_backfill(household_id: Optional[str] = None, limit: Optional[int] = None):
    engine, backfill_purchase_import_live_aliases, _, _, _ = _require_configured()
    with engine.begin() as conn:
        report = backfill_purchase_import_live_aliases(conn, household_id=household_id, limit=limit)
    return report


@router.post("/recompute-receipt-statuses")
def run_receipt_status_backfill(household_id: Optional[str] = None, limit: Optional[int] = None):
    engine, _, backfill_receipt_unpack_statuses, _, _ = _require_configured()
    with engine.begin() as conn:
        report = backfill_receipt_unpack_statuses(conn, household_id=household_id, limit=limit)
    return report


@router.post("/validate-receipt-status-baseline")
def run_receipt_status_baseline_validation(household_id: Optional[str] = None):
    engine, _, _, validate_receipt_status_baseline, _ = _require_configured()
    with engine.begin() as conn:
        report = validate_receipt_status_baseline(conn, household_id=household_id)
    return report


@router.post("/diagnose-receipt-status-baseline")
def run_receipt_status_baseline_diagnosis(household_id: Optional[str] = None):
    engine, _, _, _, diagnose_receipt_status_baseline = _require_configured()
    with engine.begin() as conn:
        report = diagnose_receipt_status_baseline(conn, household_id=household_id)
    return report
