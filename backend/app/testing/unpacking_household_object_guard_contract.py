"""Contract for server-side household authorization of Uitpakken objects."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.unpacking_household_object_guard import (
    authorize_purchase_import_request,
    install_unpacking_household_object_guard,
    resolve_purchase_import_household,
)


def _expect_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
        return
    raise AssertionError(f"Verwachte HTTP {status_code} bleef uit")


def _create_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _seed(engine) -> None:
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


def _require_context(authorization, requested_household_id):
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


def _run_http_contract(engine) -> None:
    app = FastAPI()
    endpoint_calls: list[str] = []

    @app.post("/api/purchase-import-lines/{line_id}/map")
    def map_line(line_id: str):
        endpoint_calls.append(line_id)
        return {"line_id": line_id, "executed": True}

    @app.post("/api/purchase-import-batches/{batch_id}/complete-review")
    def complete_review(batch_id: str):
        endpoint_calls.append(batch_id)
        return {"batch_id": batch_id, "executed": True}

    @app.get("/api/testing/diagnostics/purchase-import-batches/{batch_id}")
    def testing_route(batch_id: str):
        return {"batch_id": batch_id, "testing": True}

    main_module = SimpleNamespace(
        app=app,
        engine=engine,
        require_household_context=_require_context,
    )
    install_unpacking_household_object_guard(main_module)

    with TestClient(app) as client:
        own = client.post(
            "/api/purchase-import-lines/line-a/map",
            headers={"Authorization": "Bearer token-a"},
        )
        assert own.status_code == 200, own.text
        assert own.json()["executed"] is True
        assert endpoint_calls == ["line-a"]

        cross_household = client.post(
            "/api/purchase-import-lines/line-b/map",
            headers={"Authorization": "Bearer token-a"},
        )
        assert cross_household.status_code == 403, cross_household.text
        assert endpoint_calls == ["line-a"], "Endpoint werd ondanks 403 uitgevoerd"

        missing_auth = client.post(
            "/api/purchase-import-batches/batch-a/complete-review",
        )
        assert missing_auth.status_code == 401, missing_auth.text
        assert endpoint_calls == ["line-a"], "Endpoint werd ondanks 401 uitgevoerd"

        missing_object = client.post(
            "/api/purchase-import-lines/missing/map",
            headers={"Authorization": "Bearer token-a"},
        )
        assert missing_object.status_code == 404, missing_object.text
        assert endpoint_calls == ["line-a"], "Endpoint werd ondanks 404 uitgevoerd"

        testing = client.get(
            "/api/testing/diagnostics/purchase-import-batches/batch-a",
        )
        assert testing.status_code == 200, testing.text
        assert testing.json()["testing"] is True


def run_contract() -> None:
    engine = _create_engine()
    _seed(engine)

    with engine.begin() as conn:
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

        def recording_require_context(authorization, requested_household_id):
            calls.append((authorization, requested_household_id))
            return _require_context(authorization, requested_household_id)

        context = authorize_purchase_import_request(
            conn,
            "/api/purchase-import-lines/line-a/map",
            "Bearer token-a",
            recording_require_context,
        )
        assert context and context["active_household_id"] == "household-a"
        assert calls[-1] == ("Bearer token-a", "household-a")

        _expect_http_error(
            403,
            lambda: authorize_purchase_import_request(
                conn,
                "/api/purchase-import-lines/line-b/create-article",
                "Bearer token-a",
                recording_require_context,
            ),
        )
        _expect_http_error(
            401,
            lambda: authorize_purchase_import_request(
                conn,
                "/api/purchase-import-batches/batch-a/complete-review",
                None,
                recording_require_context,
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
        assert resolve_purchase_import_household(conn, "/api/receipts") is None

    _run_http_contract(engine)
    print("UNPACKING_HOUSEHOLD_OBJECT_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
