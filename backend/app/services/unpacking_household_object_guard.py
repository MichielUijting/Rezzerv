from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

_LINE_PATH = re.compile(r"^/api/purchase-import-lines/([^/]+)(?:/|$)")
_BATCH_PATH = re.compile(r"^/api/purchase-import-batches/([^/]+)(?:/|$)")


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
    request_path: str,
    authorization: str | None,
    require_household_context: Callable[[str | None, str | None], dict[str, Any]],
) -> dict[str, Any] | None:
    """Authorize a protected request against the server-side owning household."""

    household_id = resolve_purchase_import_household(conn, request_path)
    if household_id is None:
        return None
    return require_household_context(authorization, household_id)


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
                    request.url.path,
                    request.headers.get("authorization"),
                    main_module.require_household_context,
                )
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers or None,
            )
        return await call_next(request)

    app.state.unpacking_household_object_guard_installed = True
