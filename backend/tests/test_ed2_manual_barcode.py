"""No stock, receipt, or household mutation for manual ED2 GTIN evidence."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_routes
from app.services.barcode_identity_service import calculate_gtin_check_digit


def valid_gtin(body="871234567890"):
    return body + str(calculate_gtin_check_digit(body))


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar(self):
        row = self.first()
        return row if not isinstance(row, dict) else next(iter(row.values())) if row else None

    def mappings(self):
        return self

    def all(self):
        return self.rows


class Connection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.manual = {}
        self.active = False
        self.sql_log = []
        self.household_articles = [{"id": "h1", "stock": 4}]
        self.receipt_lines = [{"id": "r1", "label": "Melk"}]
        self.inventory_events = [{"id": "e1"}]

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        self.sql_log.append(sql)
        if sql.startswith("SELECT id FROM external_article_product_links"):
            return Result([{"id": "active"}] if self.active else [])
        if sql.startswith("SELECT gtin FROM ed2_manual_barcodes"):
            key = (params["retailer_code"], params["receipt_text_normalized"],
                   params["external_article_code"])
            return Result([self.manual[key]] if key in self.manual else [])
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            return Result([1])
        if sql.startswith("INSERT INTO ed2_manual_barcodes"):
            key = (params["retailer_code"], params["receipt_text_normalized"],
                   params["external_article_code"])
            self.manual[key] = params["gtin"]
            return Result([])
        if sql.startswith("SELECT retailer_code, receipt_text_normalized, external_article_code, gtin"):
            return Result([{
                "retailer_code": key[0], "receipt_text_normalized": key[1],
                "external_article_code": key[2], "gtin": gtin,
            } for key, gtin in self.manual.items()])
        raise AssertionError("Onverwachte SQL: " + sql)


class Engine:
    def __init__(self):
        self.conn = Connection()

    @contextmanager
    def begin(self):
        yield self.conn

    @contextmanager
    def connect(self):
        yield self.conn


@pytest.fixture
def guard(monkeypatch):
    engine = Engine()
    permissions = []
    search_calls = []
    linked = []
    source = {"retailer_code": "Jumbo", "receipt_text": "Melk",
              "external_article_code": " 123 "}
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {
        "ed2_manual_barcodes", "external_article_product_links", "global_products",
    })
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda key: permissions.append(key))
    monkeypatch.setattr(catalog_routes, "resolve_external_article_identity",
                        lambda conn, receipt_item_id: source if receipt_item_id == "receipt-table-line:r1"
                        else (_ for _ in ()).throw(ValueError("not found")))

    def search(payload):
        search_calls.append(payload)
        return {"results": []}

    def link(payload):
        linked.append(payload)
        return {"ok": True, "classification_pending": True}

    monkeypatch.setattr(catalog_routes, "search_off_candidates", search)
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", link)
    return engine.conn, permissions, search_calls, linked, monkeypatch


def save(code):
    return catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=code,
        )
    )


def test_unknown_off_barcode_records_only_standalone_evidence(guard):
    conn, permissions, search_calls, linked, _ = guard
    before_household = [dict(x) for x in conn.household_articles]
    before_receipt = [dict(x) for x in conn.receipt_lines]
    before_events = [dict(x) for x in conn.inventory_events]
    gtin = valid_gtin()
    result = save(gtin)
    assert result == {"saved": True, "source": "manual", "gtin": gtin,
                      "off_found": False, "classification_pending": False,
                      "photo_loaded": False}
    assert permissions == ["platform.external_products.link_existing"]
    assert search_calls == [{"receipt_item_id": "receipt-table-line:r1",
                             "mode": "manual", "gtin": gtin, "limit": 1}]
    assert conn.manual == {("jumbo", "melk", "123"): gtin}
    assert not linked
    assert conn.household_articles == before_household
    assert conn.receipt_lines == before_receipt
    assert conn.inventory_events == before_events
    assert len([x for x in conn.sql_log if x.startswith("INSERT")]) == 1
    assert save(gtin)["saved"] is True
    assert len([x for x in conn.sql_log if x.startswith("INSERT")]) == 1


def test_off_result_reuses_signed_proof_not_browser_metadata(guard):
    conn, _, search_calls, linked, monkeypatch = guard
    code = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": code, "selection_proof": "server-signed",
                     "identity_compatible": True, "image_url": "https://example.test/image.jpg"}],
    })
    result = save(code)
    assert result["saved"] is True
    assert result["off_found"] is True
    assert result["photo_loaded"] is True
    assert result["classification_pending"] is True
    assert linked == [{"receipt_item_id": "receipt-table-line:r1",
                       "gtin": code, "selection_proof": "server-signed"}]
    assert conn.manual == {}
    assert not search_calls


@pytest.mark.parametrize("error_case", ["bad_checksum", "collision", "active_link", "off_conflict"])
def test_conflict_and_invalid_input_never_write_manual_barcode(guard, error_case):
    conn, _, _, linked, monkeypatch = guard
    code = valid_gtin()
    if error_case == "bad_checksum":
        with pytest.raises(HTTPException) as err:
            save(code[:-1] + str((int(code[-1]) + 1) % 10))
        assert err.value.status_code == 422
    else:
        if error_case == "collision":
            conn.manual[("jumbo", "melk", "123")] = valid_gtin("871234567891")
        elif error_case == "active_link":
            conn.active = True
        else:
            monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
                "results": [{"identity_compatible": False, "selection_proof": "proof"}],
            })
        with pytest.raises(HTTPException) as err:
            save(code)
        assert err.value.status_code == 409
    assert not linked
    if error_case != "collision":
        assert conn.manual == {}


def test_permission_is_required_before_any_database_access(guard, monkeypatch):
    conn, permissions, _, _, _ = guard

    def deny(permission):
        assert permission == "platform.external_products.link_existing"
        raise HTTPException(status_code=403, detail="denied")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", deny)
    with pytest.raises(HTTPException) as error:
        save(valid_gtin())
    assert error.value.status_code == 403
    assert not conn.sql_log


def test_unknown_source_is_not_registered(guard):
    conn, _, _, _, _ = guard
    with pytest.raises(HTTPException) as error:
        catalog_routes.save_ed2_manual_barcode(catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:not-exists", gtin=valid_gtin(),
        ))
    assert error.value.status_code == 404
    assert conn.manual == {}
