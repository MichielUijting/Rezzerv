from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, Query

from app.db import engine
from app.services.household_context_adapter import household_context_from_runtime_context
from app.services.loyalty_stamp_read_service import (
    list_loyalty_stamp_programs_for_household,
    list_loyalty_stamp_transactions_for_household,
)

router = APIRouter()


def _authorized_household_id(authorization: str | None) -> str:
    # Lazy import avoids a circular import while reusing the central runtime policy.
    from app.main import require_household_context

    runtime_context = require_household_context(authorization)
    household_context = household_context_from_runtime_context(runtime_context)
    return household_context.active_household_id


@router.get('/api/loyalty-stamps/programs')
def loyalty_stamp_programs(
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    with engine.begin() as conn:
        programs = list_loyalty_stamp_programs_for_household(conn, household_id)
    return {
        'household_id': household_id,
        'programs': programs,
    }


@router.get('/api/loyalty-stamps/transactions')
def loyalty_stamp_transactions(
    stamp_program_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    authorization: Optional[str] = Header(None),
):
    household_id = _authorized_household_id(authorization)
    with engine.begin() as conn:
        transactions = list_loyalty_stamp_transactions_for_household(
            conn,
            household_id,
            stamp_program_code=stamp_program_code,
            limit=limit,
        )
    return {
        'household_id': household_id,
        'transactions': transactions,
        'count': len(transactions),
    }
