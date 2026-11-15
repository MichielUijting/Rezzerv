"""Bounded, server-owned matching of independently proven receipt identities.

Not an HTTP endpoint. Unprivileged receipt ingestion may wake the worker only
after its transaction commits; it cannot supply a product ID or impersonate a
Superuser. Missing in-process signals are recovered by a periodic server scan.
"""
from __future__ import annotations

import asyncio
import logging
from threading import Event

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.article_recognition_service_actor import SERVICE_ACTOR_ID

LOG = logging.getLogger(__name__)

# Event only: no credentials, household IDs or raw bonnen are cached here.
_RECEIPT_COMMITTED = Event()
_GLOBAL_AUTO_WORKER_LOCK = 753909141
_STARTUP_DELAY_SECONDS = 20
_RETRY_INTERVAL_SECONDS = 15 * 60
_MAX_PASSES_PER_WAKE = 8


def signal_receipt_committed() -> None:
    """Non-blocking post-commit wake-up; repeated signals coalesce safely."""
    _RECEIPT_COMMITTED.set()


def perform_recognition_pass(conn) -> dict:
    """One serialized transaction. Never accepts any caller-supplied identity."""
    if getattr(getattr(conn, "dialect", None), "name", "") != "postgresql":
        return {"status": "unavailable", "linked": 0, "limit_reached": False}
    status = conn.execute(text("SELECT state FROM maintenance_control WHERE id=1")).scalar_one_or_none()
    if status not in {"normal", "announced"}:
        return {"status": "paused", "linked": 0, "limit_reached": False}
    acquired = conn.execute(text(
        "SELECT pg_try_advisory_xact_lock(:lock)"
    ), {"lock": _GLOBAL_AUTO_WORKER_LOCK}).scalar_one()
    if acquired is not True:
        return {"status": "busy", "linked": 0, "limit_reached": False}

    # These are the EXACT same evidence/commit authorities as the Superuser's
    # Matchen POST. The curated matcher in system mode deliberately excludes
    # variant creation/synonym edges requiring a human approval.
    from app.services.automatic_curated_identity_matching_service import automatically_match_curated_receipts
    from app.services.proven_exact_receipt_name_service import automatically_match_proven_exact_names
    family = automatically_match_curated_receipts(
        conn, actor_id=SERVICE_ACTOR_ID, actor_type="system_service"
    )
    names = automatically_match_proven_exact_names(
        conn, actor_id=SERVICE_ACTOR_ID, actor_type="system_service"
    )
    if (family.get("ok") is not True or names.get("ok") is not True
        or family.get("barcode_written") is not False
        or names.get("barcode_written") is not False
        or int(family.get("synonyms_created") or 0) != 0):
        raise RuntimeError("Interne herkenningscontrole gaf geen veilig resultaat.")
    linked = int(family.get("linked") or 0) + int(names.get("linked") or 0)
    if linked < 0:
        raise RuntimeError("Ongeldige herkenningssamenvatting.")
    return {"status": "applied", "linked": linked,
            "limit_reached": bool(family.get("limit_reached") or names.get("limit_reached"))}


def run_one_recognition_pass(engine: Engine) -> dict:
    """Maintenance-admitted private call; no household session or API actor."""
    if engine.dialect.name != "postgresql":
        return {"status": "unavailable", "linked": 0, "limit_reached": False}
    # The maintenance infrastructure depends on full application/Alembic
    # startup contracts. Import it only for a live PostgreSQL write, not
    # while importing read-only test helpers in isolated CI environments.
    from app.services.maintenance_runtime import writer_operation

    @writer_operation
    def admitted_pass():
        with engine.begin() as conn:
            return perform_recognition_pass(conn)

    return admitted_pass()


async def _recognition_worker(engine: Engine, stop: asyncio.Event) -> None:
    # Startup should never wait for a full ED2 scan. A periodic scan also
    # recovers any post-commit signal lost to shutdown / another worker process.
    try:
        await asyncio.wait_for(stop.wait(), timeout=_STARTUP_DELAY_SECONDS)
        return
    except asyncio.TimeoutError:
        _RECEIPT_COMMITTED.set()
    while not stop.is_set():
        await asyncio.to_thread(_RECEIPT_COMMITTED.wait, _RETRY_INTERVAL_SECONDS)
        _RECEIPT_COMMITTED.clear()
        if stop.is_set():
            break
        try:
            last = None
            for _ in range(_MAX_PASSES_PER_WAKE):
                if stop.is_set():
                    break
                last = await asyncio.to_thread(run_one_recognition_pass, engine)
                if last.get("status") != "applied" or last.get("linked", 0) == 0:
                    break
            # Bounded work per wake, but continue after any genuinely new
            # evidence; no infinite busy-loop on persistent conflicts.
            if last and last.get("status") == "applied" and last.get("linked", 0) > 0:
                _RECEIPT_COMMITTED.set()
        except Exception as exc:
            # Raw receipts, account IDs, product names and connection details
            # must not be copied into general application logs.
            LOG.warning("Interne artikelherkenning niet afgerond (%s)", type(exc).__name__)


def register_article_recognition_worker(app, engine: Engine) -> None:
    """Register one lifecycle-managed private task per application process."""
    if getattr(app.state, "article_recognition_registered", False):
        return
    app.state.article_recognition_registered = True

    async def on_startup():
        stop = asyncio.Event()
        app.state.article_recognition_stop = stop
        app.state.article_recognition_task = asyncio.create_task(
            _recognition_worker(engine, stop)
        )

    async def on_shutdown():
        stop = getattr(app.state, "article_recognition_stop", None)
        if stop is not None:
            stop.set()
        _RECEIPT_COMMITTED.set()
        task = getattr(app.state, "article_recognition_task", None)
        if task is not None:
            await task

    app.add_event_handler("startup", on_startup)
    app.add_event_handler("shutdown", on_shutdown)
