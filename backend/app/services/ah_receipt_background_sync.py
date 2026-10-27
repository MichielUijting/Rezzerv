"""Bounded household-scoped AH background receipt sync.

Uses only the existing encrypted AH account source. Never reads provider passwords,
browser sessions or records of any other retailer. The PostgreSQL advisory lock
prevents concurrent background jobs from importing for one household.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.maintenance_runtime import writer_operation

LOGGER = logging.getLogger(__name__)
AH_AUTO_SYNC_INTERVAL_SECONDS = 15 * 60
AH_AUTO_SYNC_STARTUP_DELAY_SECONDS = 60
AH_AUTO_SYNC_LIMIT = 100
AH_MAINTENANCE_POLL_SECONDS = 5


def _imports_allowed(engine: Engine) -> bool:
    """Read the durable admission state; an absent state must stop scheduling."""
    with engine.connect() as conn:
        value = conn.execute(text(
            "SELECT state FROM maintenance_control WHERE id=1"
        )).scalar_one_or_none()
    return value in {"normal", "announced"}


def _lock_key(household_id: str) -> int:
    payload = b"inhuis:ah:background:" + household_id.encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=True)


def _due(last_sync_at, now: datetime) -> bool:
    if last_sync_at is None:
        return True
    if not isinstance(last_sync_at, datetime):
        return False
    if last_sync_at.tzinfo is None:
        last_sync_at = last_sync_at.replace(tzinfo=timezone.utc)
    return now - last_sync_at >= timedelta(seconds=AH_AUTO_SYNC_INTERVAL_SECONDS)


@writer_operation
def _admitted_ah_sync(engine: Engine, receipt_root: Path, household_id: str) -> None:
    # Admission is durable until the entire receipt import finishes.
    # During server maintenance, the existing write barrier refuses new work.
    # Import on the actual execution path, not during application registration
    # or isolated contract tests; failures remain behind maintenance admission.
    from app.services.ah_receipt_sync_service import sync_ah_receipts
    sync_ah_receipts(
        engine,
        receipt_root,
        household_id=household_id,
        limit=AH_AUTO_SYNC_LIMIT,
    )


def sync_due_ah_households(
    engine: Engine, receipt_root: Path, stop_requested: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """One safe iteration; PostgreSQL session locks protect multiple API workers."""
    result = {"due": 0, "completed": 0, "failed": 0, "locked": 0}
    if engine.dialect.name != "postgresql":
        return result

    if not _imports_allowed(engine):
        return result

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT household_id, last_sync_at
            FROM retailer_account_credentials
            WHERE provider = 'ah'
            ORDER BY household_id
        """)).mappings().all()

    now = datetime.now(timezone.utc)
    for row in rows:
        # Re-check between households; a running receipt import completes
        # safely, while subsequent households do not start during draining.
        if (stop_requested is not None and stop_requested()) or not _imports_allowed(engine):
            break
        household_id = str(row.get("household_id") or "").strip()
        if not household_id or not _due(row.get("last_sync_at"), now):
            continue
        result["due"] += 1
        with engine.connect() as lock_conn:
            key = _lock_key(household_id)
            acquired = bool(lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": key}
            ).scalar())
            if not acquired:
                result["locked"] += 1
                continue
            try:
                # Recheck freshness under the lock: another API process may
                # already have finished this household while we were waiting.
                last_run = lock_conn.execute(text("""
                    SELECT last_sync_at
                    FROM retailer_account_credentials
                    WHERE provider = 'ah' AND household_id = :household_id
                """), {"household_id": household_id}).scalar_one_or_none()
                if not _due(last_run, datetime.now(timezone.utc)):
                    continue
                try:
                    _admitted_ah_sync(engine, receipt_root, household_id)
                except Exception:
                    # Fail closed for this household. Do not log provider errors,
                    # access tokens, receipt IDs or potentially sensitive bodies.
                    LOGGER.warning("AH background sync failed for one household")
                    result["failed"] += 1
                else:
                    result["completed"] += 1
            finally:
                lock_conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": key}
                )
    return result


async def run_ah_background_sync(engine: Engine, receipt_root: Path, stop: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=AH_AUTO_SYNC_STARTUP_DELAY_SECONDS)
        return
    except asyncio.TimeoutError:
        pass

    was_paused = False
    next_run = 0.0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        try:
            allowed = await asyncio.to_thread(_imports_allowed, engine)
            if not allowed:
                was_paused = True
            elif was_paused or loop.time() >= next_run:
                await asyncio.to_thread(sync_due_ah_households, engine, receipt_root, stop.is_set)
                was_paused = False
                next_run = loop.time() + AH_AUTO_SYNC_INTERVAL_SECONDS
        except Exception:
            LOGGER.warning("AH background sync iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=AH_MAINTENANCE_POLL_SECONDS)
        except asyncio.TimeoutError:
            pass


def register_ah_background_sync(app, engine: Engine, receipt_root: Path) -> None:
    """Register a background task; do not block app startup or start a new DB."""
    @app.on_event("startup")
    async def start_ah_background_sync() -> None:
        stop = asyncio.Event()
        app.state.ah_background_stop = stop
        app.state.ah_background_task = asyncio.create_task(
            run_ah_background_sync(engine, receipt_root, stop)
        )

    @app.on_event("shutdown")
    async def stop_ah_background_sync() -> None:
        stop = getattr(app.state, "ah_background_stop", None)
        task = getattr(app.state, "ah_background_task", None)
        if stop is not None:
            stop.set()
        if task is not None:
            await task
