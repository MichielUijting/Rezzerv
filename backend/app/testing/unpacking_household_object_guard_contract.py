"""Contract for server-side household authorization of Uitpakken objects."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.unpacking_household_object_guard import (
    authorize_purchase_import_request,
    resolve_purchase_import_household,
)


def _expect_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
        return
    raise AssertionError(f"Verwachte HTTP {status_code} bleef uit")


def run_contract() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE purchase_import_batches (
                    id TEXT PRIMARY KEY,
                    household_id TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE purchase_import_lines (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_batches (id, household_id)
                VALUES ('batch-a', 'household-a'), ('batch-b', 'household-b')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_lines (id, batch_id)
                VALUES ('line-a', 'batch-a'), ('line-b', 'batch-b')
                """
            )
        )

        assert (
            resolve_purchase_import_household(
                conn,
                "/api/purchase-import-lines/line-a/map",
            )
            == "household-a"
        )
        assert (
            resolve_purchase_import_household(
                conn,
                "/api/purchase-import-batches/batch-b/process",
            )
            == "household-b"
        )

        calls: list[tuple[str | None, str | None]] = []

        def require_context(authorization, requested_household_id):
            calls.append((authorization, requested_household_id))
            token_household = {
                "Bearer token-a": "household-a",
                "Bearer token-b": "household-b",
            }.get(authorization)
            if token_household is None:
                raise HTTPException(status_code=401, detail="Unauthorized")
            if token_household != requested_household_id:
                raise HTTPException(status_code=403, detail="Geen toegang")
            return {
                "active_household_id": token_household,
                "display_role": "admin",
            }

        context = authorize_purchase_import_request(
            conn,
            "/api/purchase-import-lines/line-a/map",
            "Bearer token-a",
            require_context,
        )
        assert context and context["active_household_id"] == "household-a"
        assert calls[-1] == ("Bearer token-a", "household-a")

        _expect_http_error(
            403,
            lambda: authorize_purchase_import_request(
                conn,
                "/api/purchase-import-lines/line-b/create-article",
                "Bearer token-a",
                require_context,
            ),
        )
        _expect_http_error(
            401,
            lambda: authorize_purchase_import_request(
                conn,
                "/api/purchase-import-batches/batch-a/complete-review",
                None,
                require_context,
            ),
        )
        _expect_http_error(
            404,
            lambda: resolve_purchase_import_household(
                conn,
                "/api/purchase-import-lines/missing/map",
            ),
        )
        _expect_http_error(
            404,
            lambda: resolve_purchase_import_household(
                conn,
                "/api/purchase-import-batches/missing/process",
            ),
        )

        assert (
            resolve_purchase_import_household(
                conn,
                "/api/testing/diagnostics/purchase-import-batches/batch-a",
            )
            is None
        )
        assert (
            resolve_purchase_import_household(conn, "/api/receipts")
            is None
        )

    print("UNPACKING_HOUSEHOLD_OBJECT_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
