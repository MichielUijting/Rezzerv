"""Contract for server-side household and write authorization of Uitpakken objects."""

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
    token_context = {
        "Bearer token-a-admin": ("household-a", "admin"),
        "Bearer token-a-viewer": ("household-a", "viewer"),
        "Bearer token-b-admin": ("household-b", "admin"),
    }.get(authorization)
    if token_context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    token_household, display_role = token_context
    if token_household != requested_household_id:
        raise HTTPException(status_code=403, detail="Geen toegang")
    return {
        "active_household_id": token_household,
        "display_role": display_role,
    }


def _require_write_context(authorization, requested_household_id):
    context = _require_context(authorization, requested_household_id)
    if context["display_role"] == "viewer":
        raise HTTPException(status_code=403, detail="Kijkers mogen deze voorraadactie niet uitvoeren")
    return context


def _run_http_contract(engine) -> None:
    app = FastAPI()
    endpoint_calls: list[str] = []

    @app.post("/api/purchase-import-lines/{line_id}/map")
    def map_line(line_id: str):
        endpoint_calls.append(f"map:{line_id}")
        return {"line_id": line_id, "executed": True}

    @app.post("/api/purchase-import-lines/{line_id}/external-product-candidates/search")
    def search_candidates(line_id: str):
        endpoint_calls.append(f"search:{line_id}")
        return {"line_id": line_id, "executed": True}

    @app.get("/api/purchase-import-lines/{line_id}/external-product-candidates")
    def get_candidates(line_id: str):
        endpoint_calls.append(f"read:{line_id}")
        return {"line_id": line_id, "executed": True}

    @app.post("/api/purchase-import-batches/{batch_id}/complete-review")
    def complete_review(batch_id: str):
        endpoint_calls.append(f"complete:{batch_id}")
        return {"batch_id": batch_id, "executed": True}

    @app.get("/api/testing/diagnostics/purchase-import-batches/{batch_id}")
    def testing_route(batch_id: str):
        return {"batch_id": batch_id, "testing": True}

    main_module = SimpleNamespace(
        app=app,
        engine=engine,
        require_household_context=_require_context,
        require_inventory_write_context=_require_write_context,
    )
    install_unpacking_household_object_guard(main_module)

    with TestClient(app) as client:
        own_write = client.post(
            "/api/purchase-import-lines/line-a/map",
            headers={"Authorization": "Bearer token-a-admin"},
        )
        assert own_write.status_code == 200, own_write.text
        assert own_write.json()["executed"] is True
        assert endpoint_calls == ["map:line-a"]

        viewer_write = client.post(
            "/api/purchase-import-lines/line-a/map",
            headers={"Authorization": "Bearer token-a-viewer"},
        )
        assert viewer_write.status_code == 403, viewer_write.text
        assert endpoint_calls == ["map:line-a"], "Map-endpoint werd ondanks kijkersblokkering uitgevoerd"

        viewer_search = client.post(
            "/api/purchase-import-lines/line-a/external-product-candidates/search",
            headers={"Authorization": "Bearer token-a-viewer"},
        )
        assert viewer_search.status_code == 403, viewer_search.text
        assert endpoint_calls == ["map:line-a"], "Zoekendpoint werd ondanks kijkersblokkering uitgevoerd"

        viewer_read = client.get(
            "/api/purchase-import-lines/line-a/external-product-candidates",
            headers={"Authorization": "Bearer token-a-viewer"},
        )
        assert viewer_read.status_code == 200, viewer_read.text
        assert viewer_read.json()["executed"] is True
        assert endpoint_calls == ["map:line-a", "read:line-a"]

        cross_household = client.post(
            "/api/purchase-import-lines/line-b/map",
            headers={"Authorization": "Bearer token-a-admin"},
        )
        assert cross_household.status_code == 403, cross_household.text
        assert endpoint_calls == ["map:line-a", "read:line-a"], "Endpoint werd ondanks 403 uitgevoerd"

        missing_auth = client.post(
            "/api/purchase-import-batches/batch-a/complete-review",
        )
        assert missing_auth.status_code == 401, missing_auth.text
        assert endpoint_calls == ["map:line-a", "read:line-a"], "Endpoint werd ondanks 401 uitgevoerd"

        missing_object = client.post(
            "/api/purchase-import-lines/missing/map",
            headers={"Authorization": "Bearer token-a-admin"},
        )
        assert missing_object.status_code == 404, missing_object.text
        assert endpoint_calls == ["map:line-a", "read:line-a"], "Endpoint werd ondanks 404 uitgevoerd"

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

        read_calls: list[tuple[str | None, str | None]] = []
        write_calls: list[tuple[str | None, str | None]] = []

        def recording_require_context(authorization, requested_household_id):
            read_calls.append((authorization, requested_household_id))
            return _require_context(authorization, requested_household_id)

        def recording_require_write_context(authorization, requested_household_id):
            write_calls.append((authorization, requested_household_id))
            return _require_write_context(authorization, requested_household_id)

        read_context = authorize_purchase_import_request(
            conn,
            "GET",
            "/api/purchase-import-lines/line-a/external-product-candidates",
            "Bearer token-a-viewer",
            recording_require_context,
            recording_require_write_context,
        )
        assert read_context and read_context["display_role"] == "viewer"
        assert read_calls[-1] == ("Bearer token-a-viewer", "household-a")
        assert write_calls == []

        write_context = authorize_purchase_import_request(
            conn,
            "POST",
            "/api/purchase-import-lines/line-a/map",
            "Bearer token-a-admin",
            recording_require_context,
            recording_require_write_context,
        )
        assert write_context and write_context["display_role"] == "admin"
        assert write_calls[-1] == ("Bearer token-a-admin", "household-a")

        _expect_http_error(
            403,
            lambda: authorize_purchase_import_request(
                conn,
                "POST",
                "/api/purchase-import-lines/line-a/external-product-candidates/search",
                "Bearer token-a-viewer",
                recording_require_context,
                recording_require_write_context,
            ),
        )
        _expect_http_error(
            403,
            lambda: authorize_purchase_import_request(
                conn,
                "POST",
                "/api/purchase-import-lines/line-b/create-article",
                "Bearer token-a-admin",
                recording_require_context,
                recording_require_write_context,
            ),
        )
        _expect_http_error(
            401,
            lambda: authorize_purchase_import_request(
                conn,
                "POST",
                "/api/purchase-import-batches/batch-a/complete-review",
                None,
                recording_require_context,
                recording_require_write_context,
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
