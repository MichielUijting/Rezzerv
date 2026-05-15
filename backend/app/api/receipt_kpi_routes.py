from __future__ import annotations

from fastapi import APIRouter

from app.db import engine
from receipt_ingestion.kassa_kpi_baseline import build_kassa_kpi_baseline
from receipt_ingestion.kassa_kpi_scope_diagnosis import build_kassa_kpi_scope_diagnosis

router = APIRouter(
    prefix='/api/receipt-kpi',
    tags=['receipt-kpi'],
)


@router.get('/baseline')
def get_receipt_kpi_baseline():
    """Read-only KPI summary for the existing Kassa/SSOT flow.

    This endpoint does not change receipt status and does not write to the DB.
    It only measures how many active receipts currently reach Gecontroleerd.
    """
    with engine.begin() as conn:
        return build_kassa_kpi_baseline(conn)


@router.get('/scope-diagnosis')
def get_receipt_kpi_scope_diagnosis():
    """Explain why the KPI scope may be empty.

    Read-only diagnostic endpoint.
    Does not restore archived receipts or modify receipt status.
    """
    with engine.begin() as conn:
        return build_kassa_kpi_scope_diagnosis(conn)
