"""Screen-independent, bounded ED2 Superuser matching progress (in-process).

The HTTP session only authorizes starting/reading the task. Each pass executes
through the established database transaction, maintenance and identity guards.
There is no new schema or process-specific database identity. A backend restart
loses the transient progress record, but each completed batch is committed.
"""
from __future__ import annotations

import logging
from threading import Lock, Thread
from uuid import uuid4

LOG = logging.getLogger(__name__)
_GUARD = Lock()
_JOB = None
_MAX_PASSES = 100


def _public(job):
    response = {key: value for key, value in job.items()
                if key not in {"actor_id", "matching_overview"}}
    if job["state"] == "completed" and job.get("matching_overview") is not None:
        response["matching_overview"] = job["matching_overview"]
    return {"ok": True, **response}


def _publish(job, **changes):
    with _GUARD:
        job.update(changes)


def current_matching_progress():
    with _GUARD:
        if _JOB is None:
            return {"ok": False, "state": "not_started"}
        return _public(_JOB)


def start_matching_progress(engine, actor_id, run_pass):
    """At most one active local process job; no duplicated browser work."""
    global _JOB
    if not actor_id:
        raise ValueError("Een geautoriseerde Superuser ontbreekt.")
    with _GUARD:
        if _JOB is not None and _JOB["state"] == "running":
            return _public(_JOB)
        job = dict(id=uuid4().hex, actor_id=actor_id, state="running",
                   phase="voorbereiden", pass_number=1, checked=0, total=0,
                   matched=0, error="", matching_overview=None)
        _JOB = job
    try:
        if getattr(getattr(engine, "dialect", None), "name", None) == "postgresql":
            # Reserve a durable maintenance operation BEFORE detaching the
            # browser request; maintenance draining must wait for this worker.
            from app.services.maintenance_runtime import start_worker
            start_worker(target=_run, args=(job, engine, actor_id, run_pass),
                         daemon=True, name="ed2-match-progress", engine=engine)
        else:
            Thread(target=_run, args=(job, engine, actor_id, run_pass),
                   daemon=True, name="ed2-match-progress").start()
    except Exception:
        _publish(job, state="error", error="De achtergrondcontrole kon niet starten.")
    return current_matching_progress()


def _run(job, engine, actor_id, run_pass):
    try:
        for number in range(1, _MAX_PASSES + 1):
            _publish(job, pass_number=number, phase="voorbereiden",
                     checked=0, total=0)
            def update(phase, checked, total):
                if (not isinstance(checked, int) or not isinstance(total, int)
                        or checked < 0 or total < 0 or checked > total):
                    raise ValueError("Ongeldige gecontroleerde artikelteller.")
                _publish(job, phase=phase, checked=checked, total=total)

            with engine.begin() as conn:
                family, general = run_pass(conn, actor_id, update)
                if (family.get("ok") is not True or general.get("ok") is not True
                        or family.get("barcode_written") is not False
                        or general.get("barcode_written") is not False):
                    raise ValueError("De matchingcontrole gaf geen betrouwbaar resultaat.")
                batch_linked = int(family.get("linked") or 0) + int(general.get("linked") or 0)
                limited = bool(family.get("limit_reached") or general.get("limit_reached"))
                final_overview = general.get("matching_overview") if batch_linked == 0 else None
            if batch_linked < 0:
                raise ValueError("Ongeldige matchinguitkomst.")
            with _GUARD:
                job["matched"] += batch_linked
            if batch_linked == 0 and limited:
                raise ValueError("De matching heeft geen voortgang in een begrensde batch.")
            if batch_linked == 0 and not limited:
                _publish(job, state="completed", phase="afgerond",
                         matching_overview=final_overview)
                return
        raise ValueError("Het maximum van 100 automatische controlerondes is bereikt.")
    except Exception as exc:
        LOG.warning("ED2 achtergrondcontrole niet afgerond (%s)", type(exc).__name__)
        message = (str(exc) if isinstance(exc, ValueError)
                   else "De matchingcontrole is onverwacht onderbroken.")
        _publish(job, state="error", error=message)
