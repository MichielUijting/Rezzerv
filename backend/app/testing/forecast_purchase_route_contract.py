from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.platform_admin_route_guard import PROTECTED_MUTATIONS
from app.services.unpacking_household_object_guard import authorize_purchase_import_request
from app.testing.forecast_purchase_route_audit import audit_routes


EXPECTED_ROUTE_KEYS = {
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("GET", "/api/household/almost-out-settings"),
    ("PUT", "/api/household/almost-out-settings"),
    ("GET", "/api/household/store-import-settings"),
    ("PUT", "/api/household/store-import-settings"),
    ("GET", "/api/households/{household_id}/almost-out"),
    ("GET", "/api/purchase-import-batches/{batch_id}"),
    ("POST", "/api/purchase-import-batches/{batch_id}/complete-review"),
    ("POST", "/api/purchase-import-batches/{batch_id}/prefill"),
    ("POST", "/api/purchase-import-batches/{batch_id}/process"),
    ("POST", "/api/purchase-import-lines/{line_id}/article-group"),
    ("POST", "/api/purchase-import-lines/{line_id}/create-article"),
    ("GET", "/api/purchase-import-lines/{line_id}/external-product-candidates"),
    ("POST", "/api/purchase-import-lines/{line_id}/external-product-candidates/search"),
    ("POST", "/api/purchase-import-lines/{line_id}/map"),
    ("POST", "/api/purchase-import-lines/{line_id}/review"),
    ("POST", "/api/purchase-import-lines/{line_id}/target-location"),
    ("POST", "/api/purchases/barcode"),
    ("POST", "/api/purchases/manual"),
    ("POST", "/api/store-connections/{connection_id}/pull-purchases"),
    ("GET", "/api/testing/diagnostics/purchase-import-batches/{batch_id}"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
}

PLATFORM_ADMIN_KEYS = {
    ("POST", "/api/admin/backfill-purchase-import-live-aliases"),
    ("POST", "/api/testing/regression/almost-out-prediction"),
    ("POST", "/api/testing/regression/almost-out-self-test"),
}

OBJECT_GUARD_KEYS = {
    key
    for key in EXPECTED_ROUTE_KEYS
    if key[1].startswith("/api/purchase-import-batches/")
    or key[1].startswith("/api/purchase-import-lines/")
}

INLINE_KEYS = EXPECTED_ROUTE_KEYS - PLATFORM_ADMIN_KEYS - OBJECT_GUARD_KEYS

EXPECTED_INLINE_MARKERS = {
    ("GET", "/api/household/almost-out-settings"): {"require_household_context"},
    ("PUT", "/api/household/almost-out-settings"): {"require_household_admin_context"},
    ("GET", "/api/household/store-import-settings"): {"require_household_context"},
    ("PUT", "/api/household/store-import-settings"): {"require_household_admin_context"},
    ("GET", "/api/households/{household_id}/almost-out"): {"require_household_context"},
    ("POST", "/api/purchases/barcode"): {"require_inventory_write_context"},
    ("POST", "/api/purchases/manual"): {"require_inventory_write_context"},
    ("POST", "/api/store-connections/{connection_id}/pull-purchases"): {"require_household_admin_context"},
    ("GET", "/api/testing/diagnostics/purchase-import-batches/{batch_id}"): {"require_platform_admin_user"},
}


@dataclass
class _Result:
    household_id: str

    def mappings(self) -> "_Result":
        return self

    def first(self) -> dict[str, str]:
        return {"household_id": self.household_id}


class _Connection:
    def __init__(self, household_id: str = "household-a") -> None:
        self.household_id = household_id

    def execute(self, _statement: Any, _params: dict[str, Any]) -> _Result:
        return _Result(self.household_id)


def _assert_object_guard_contract() -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def require_context(authorization: str | None, household_id: str | None) -> dict[str, str | None]:
        calls.append(("read", authorization, household_id))
        return {"active_household_id": household_id}

    def require_write(authorization: str | None, household_id: str | None) -> dict[str, str | None]:
        calls.append(("write", authorization, household_id))
        return {"active_household_id": household_id}

    conn = _Connection()
    authorize_purchase_import_request(
        conn,
        "GET",
        "/api/purchase-import-batches/batch-1",
        "Bearer member",
        require_context,
        require_write,
    )
    authorize_purchase_import_request(
        conn,
        "POST",
        "/api/purchase-import-lines/line-1/review",
        "Bearer member",
        require_context,
        require_write,
    )
    assert calls == [
        ("read", "Bearer member", "household-a"),
        ("write", "Bearer member", "household-a"),
    ], calls


def main() -> None:
    payload = audit_routes()
    rows = payload["routes"]
    route_map = {(row["method"], row["path"]): row for row in rows}
    actual_keys = set(route_map)

    assert actual_keys == EXPECTED_ROUTE_KEYS, {
        "missing": sorted(EXPECTED_ROUTE_KEYS - actual_keys),
        "unexpected": sorted(actual_keys - EXPECTED_ROUTE_KEYS),
    }
    assert payload["summary"] == {
        "route_registrations": 23,
        "reads": 6,
        "mutations": 17,
        "routes_without_auth_marker": 11,
        "mutations_without_auth_marker": 9,
    }, payload["summary"]

    assert len(OBJECT_GUARD_KEYS) == 11, OBJECT_GUARD_KEYS
    assert len(PLATFORM_ADMIN_KEYS) == 3, PLATFORM_ADMIN_KEYS
    assert len(INLINE_KEYS) == 9, INLINE_KEYS

    for key in PLATFORM_ADMIN_KEYS:
        assert key in PROTECTED_MUTATIONS, key

    for key, expected_markers in EXPECTED_INLINE_MARKERS.items():
        row = route_map[key]
        assert row["authorization_parameter"], key
        assert expected_markers.issubset(set(row["auth_markers"])), {
            "route": key,
            "expected": sorted(expected_markers),
            "actual": row["auth_markers"],
        }

    for key in OBJECT_GUARD_KEYS:
        row = route_map[key]
        assert row["path"].startswith(
            ("/api/purchase-import-batches/", "/api/purchase-import-lines/")
        ), key

    _assert_object_guard_contract()
    print("M2C2N_FORECAST_PURCHASE_ROUTE_CONTRACT_GREEN")


if __name__ == "__main__":
    main()
