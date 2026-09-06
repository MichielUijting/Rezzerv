from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

_LINE_PATH = re.compile(r"^/api/purchase-import-lines/([^/]+)(?:/|$)")
_BATCH_PATH = re.compile(r"^/api/purchase-import-batches/([^/]+)(?:/|$)")
_BATCH_PROCESS_PATH = re.compile(r"^/api/purchase-import-batches/([^/]+)/process/?$")
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def resolve_purchase_import_household(conn, request_path: str) -> str | None:
    """Resolve the owning household for protected Uitpakken production URLs."""

    normalized_path = str(request_path or "").strip()
    if normalized_path.startswith("/api/testing/"):
        return None

    line_match = _LINE_PATH.match(normalized_path)
    if line_match:
        line_id = line_match.group(1).strip()
        row = conn.execute(
            text(
                """
                SELECT pib.household_id
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                WHERE pil.id = :line_id
                LIMIT 1
                """
            ),
            {"line_id": line_id},
        ).mappings().first()
        if not row or not str(row.get("household_id") or "").strip():
            raise HTTPException(status_code=404, detail="Onbekende importregel")
        return str(row["household_id"]).strip()

    batch_match = _BATCH_PATH.match(normalized_path)
    if batch_match:
        batch_id = batch_match.group(1).strip()
        row = conn.execute(
            text(
                """
                SELECT household_id
                FROM purchase_import_batches
                WHERE id = :batch_id
                LIMIT 1
                """
            ),
            {"batch_id": batch_id},
        ).mappings().first()
        if not row or not str(row.get("household_id") or "").strip():
            raise HTTPException(
                status_code=404,
                detail="Onbekende purchase import batch",
            )
        return str(row["household_id"]).strip()

    return None


def authorize_purchase_import_request(
    conn,
    request_method: str,
    request_path: str,
    authorization: str | None,
    require_household_context: Callable[[str | None, str | None], dict[str, Any]],
    require_inventory_write_context: Callable[[str | None, str | None], dict[str, Any]],
) -> dict[str, Any] | None:
    """Authorize a production Uitpakken request against its server-side household."""

    household_id = resolve_purchase_import_household(conn, request_path)
    if household_id is None:
        return None

    normalized_method = str(request_method or "").strip().upper()
    if normalized_method in _WRITE_METHODS:
        return require_inventory_write_context(authorization, household_id)
    return require_household_context(authorization, household_id)


def acquire_purchase_import_processing_lock(
    conn,
    request_method: str,
    request_path: str,
) -> bool:
    """Serialize concurrent processing attempts for one purchase-import batch.

    The lock is deliberately PostgreSQL transaction-scoped.  A second process
    request for the same batch waits until the first request has fully completed,
    so the route starts with a fresh view of processing_status/processed_event_id
    instead of racing on the same pending snapshot.
    """

    if str(request_method or "").strip().upper() != "POST":
        return False

    process_match = _BATCH_PROCESS_PATH.match(str(request_path or "").strip())
    if not process_match:
        return False

    if str(getattr(getattr(conn, "dialect", None), "name", "") or "").lower() != "postgresql":
        return False

    batch_id = process_match.group(1).strip()
    if not batch_id:
        return False

    lock_key = f"purchase-import-batch:{batch_id}"
    conn.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"
        ),
        {"lock_key": lock_key},
    )
    return True


def install_unpacking_household_object_guard(main_module) -> None:
    """Install one HTTP guard for all production Uitpakken batch/line routes."""

    app = main_module.app
    if getattr(app.state, "unpacking_household_object_guard_installed", False):
        return

    @app.middleware("http")
    async def unpacking_household_object_guard(request, call_next):
        try:
            with main_module.engine.begin() as conn:
                authorize_purchase_import_request(
                    conn,
                    request.method,
                    request.url.path,
                    request.headers.get("authorization"),
                    main_module.require_household_context,
                    main_module.require_inventory_write_context,
                )
                lock_acquired = acquire_purchase_import_processing_lock(
                    conn,
                    request.method,
                    request.url.path,
                )
                if lock_acquired:
                    # Keep the advisory transaction lock until the route has
                    # completed and its own processing transaction has committed.
                    return await call_next(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.unpacking_household_object_guard_installed = True
