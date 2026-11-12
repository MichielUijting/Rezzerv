"""PO identity contract: saving a barcode already proves identification.

Tests use a read/write PostgreSQL-shaped in-memory double, never SQLite or a
user database. No receipt, household, stock or inventory table may be updated.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.api import catalog_routes
from app.services.barcode_identity_service import calculate_gtin_check_digit
from app.services.ed2_confirmed_barcode_service import materialize_saved_ed2_barcode


class Rows:
    def __init__(self, rows=(), rowcount=None):
        self.rows = list(rows)
        self.rowcount = len(self.rows) if rowcount is None else rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class PGFixture:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.products = []
        self.identities = []
        self.manual = []
        self.legacy = []
        self.writes = []
        self.locks = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        p = params or {}
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            self.locks.append(p["key"])
            return Rows()
        if sql.startswith("SELECT retailer_code, gtin, barcode_scope, global_product_id FROM ed2_manual_barcodes"):
            return Rows([dict(x) for x in self.manual
                         if x["retailer_code"] in p["aliases"]
                         and x["receipt_text_normalized"] == p["label"]
                         and x["external_article_code"] == p["code"]])
        if sql.startswith("SELECT id AS product_id, status, primary_gtin FROM global_products"):
            return Rows([{"product_id": x["id"], **x} for x in self.products
                         if x["primary_gtin"] == p["barcode"]])
        if sql.startswith("SELECT global_product_id AS product_id FROM product_identities"):
            if "identity_type = 'gtin'" in sql:
                return Rows([{"product_id": x["global_product_id"]} for x in self.identities
                             if x["identity_type"] == "gtin" and x["identity_value"] == p["barcode"]])
            if "identity_type = 'retailer_barcode'" in sql:
                return Rows([{"product_id": x["global_product_id"]} for x in self.identities
                             if x["identity_type"] == "retailer_barcode"
                             and x["identity_value"] == p["identity_value"]])
            return Rows([{"product_id": x["global_product_id"]} for x in self.identities
                         if x["identity_type"] == p["type"] and x["identity_value"] == p["value"]])
        if sql.startswith("SELECT id FROM global_products WHERE primary_gtin"):
            return Rows([{"id": x["id"]} for x in self.products if x["primary_gtin"] == p["barcode"]])
        if sql.startswith("SELECT id, status, primary_gtin FROM global_products WHERE id"):
            return Rows([dict(x) for x in self.products if x["id"] == p["id"]])
        if sql.startswith("SELECT id FROM global_products WHERE id"):
            return Rows([{"id": x["id"]} for x in self.products
                         if x["id"] == p["id"] and x["status"] == "active"])
        if sql.startswith("SELECT DISTINCT global_product_id AS product_id FROM external_article_product_links"):
            return Rows([{"product_id": x["global_product_id"]} for x in self.legacy
                         if x["retailer_code"] in p["aliases"] and x["external_article_code"] == p["code"]
                         and x["receipt_text_normalized"] in ("", p["label"])])
        if sql.startswith("INSERT INTO global_products"):
            self.writes.append("global_products")
            self.products.append({"id": p["id"], "status": "active",
                                  "primary_gtin": p["gtin"], "name": p["name"]})
            return Rows(rowcount=1)
        if sql.startswith("UPDATE global_products SET primary_gtin"):
            self.writes.append("global_products")
            for x in self.products:
                if x["id"] == p["id"] and not x["primary_gtin"]:
                    x["primary_gtin"] = p["gtin"]
            return Rows(rowcount=1)
        if sql.startswith("INSERT INTO product_identities"):
            self.writes.append("product_identities")
            self.identities.append({
                "global_product_id": p["product_id"], "identity_type": p["type"],
                "identity_value": p["value"],
            })
            return Rows(rowcount=1)
        if sql.startswith("INSERT INTO ed2_manual_barcodes"):
            self.writes.append("ed2_manual_barcodes")
            self.manual.append({
                "retailer_code": p["retailer"], "receipt_text_normalized": p["label"],
                "external_article_code": p["code"], "gtin": p["barcode"],
                "barcode_scope": p["scope"], "global_product_id": p["product_id"],
            })
            return Rows(rowcount=1)
        if sql.startswith("UPDATE ed2_manual_barcodes"):
            self.writes.append("ed2_manual_barcodes")
            matched = [x for x in self.manual if x["retailer_code"] == p["saved_retailer"]
                       and x["receipt_text_normalized"] == p["label"]
                       and x["external_article_code"] == p["code"]
                       and x["gtin"] == p["barcode"] and not x["global_product_id"]]
            for x in matched:
                x["global_product_id"] = p["product_id"]
                x["barcode_scope"] = p["scope"]
            return Rows(rowcount=len(matched))
        raise AssertionError("Unexpected SQL: " + sql)


def _barcode(body):
    return body + str(calculate_gtin_check_digit(body))


def save(conn, retailer="AH", label="Courgette", number="21003", barcode="8722800072026"):
    return materialize_saved_ed2_barcode(
        conn, retailer_code=retailer, receipt_text=label,
        external_article_code=number, barcode=barcode, confirmed_by="frontteam-1",
    )


def test_saved_global_barcode_creates_catalog_without_off_or_classification():
    conn = PGFixture()
    result = save(conn)
    assert result["status"] == "confirmed"
    assert result["catalog_product_created"] is True
    assert result["barcode_scope"] == "global_candidate"
    assert result["stock_changes"] == result["household_changes"] == 0
    assert len(conn.products) == len(conn.identities) == len(conn.manual) == 1
    assert conn.products[0]["primary_gtin"] == "8722800072026"
    assert conn.manual[0]["global_product_id"] == conn.products[0]["id"]
    assert conn.writes == ["global_products", "product_identities", "ed2_manual_barcodes"]
    second = save(conn)
    assert second["status"] == "already_confirmed"
    assert second["global_product_id"] == result["global_product_id"]
    assert len(conn.writes) == 3


def test_same_global_gtin_across_retailers_reuses_one_catalog_product():
    conn = PGFixture()
    ah = save(conn)
    jumbo = save(conn, retailer="Jumbo", label="Jumbo courgette", number="99001")
    assert ah["global_product_id"] == jumbo["global_product_id"]
    assert jumbo["catalog_product_created"] is False
    assert len(conn.products) == 1 and len(conn.manual) == 2


def test_lidl_restricted_barcode_stays_per_receipt_identity_and_retailer():
    conn = PGFixture()
    lidl = save(conn, retailer="Lidl", label="Courgette groen", number="123",
                barcode="2008234600001")
    other_retailer = save(conn, retailer="AH", label="Courgette groen", number="123",
                          barcode="2008234600001")
    other_label = save(conn, retailer="Lidl", label="Courgette geel", number="123",
                       barcode="2008234600001")
    assert lidl["barcode_scope"] == "restricted"
    assert len({x["global_product_id"] for x in
                (lidl, other_retailer, other_label)}) == 3
    assert all(x["primary_gtin"] is None for x in conn.products)
    assert all(x["identity_type"] == "retailer_barcode" for x in conn.identities)
    assert save(conn, retailer="Lidl", label="Courgette groen", number="123",
                barcode="2008234600001")["status"] == "already_confirmed"


def test_existing_saved_barcode_is_evidence_without_second_confirmation():
    conn = PGFixture()
    conn.manual.append({
        "retailer_code": "lidl-nederland-gmbh",
        "receipt_text_normalized": "courgette groen",
        "external_article_code": "123", "gtin": "2008234600001",
        "barcode_scope": None, "global_product_id": None,
    })
    result = save(conn, retailer="Lidl", label="Courgette groen", number="123",
                  barcode="2008234600001")
    assert result["status"] == "confirmed"
    assert len(conn.manual) == 1
    assert conn.manual[0]["global_product_id"] == result["global_product_id"]
    assert conn.manual[0]["gtin"] == "2008234600001"


def test_different_stored_barcode_requires_correction_not_implicit_overwrite():
    conn = PGFixture()
    conn.manual.append({
        "retailer_code": "ah", "receipt_text_normalized": "courgette",
        "external_article_code": "21003", "gtin": "8722800072026",
        "barcode_scope": None, "global_product_id": None,
    })
    with pytest.raises(ValueError, match="andere opgeslagen barcode"):
        save(conn, barcode=_barcode("871234567890"))
    assert not conn.writes


def test_conflicting_historic_gtin_owners_fail_closed():
    conn = PGFixture()
    code = "8722800072026"
    conn.products.append({"id": "p1", "status": "active", "primary_gtin": code})
    conn.identities.append({"global_product_id": "p2", "identity_type": "gtin",
                            "identity_value": code})
    with pytest.raises(ValueError, match="meerdere Catalogusproducten"):
        save(conn)
    assert not conn.writes


def test_normal_route_never_calls_off_or_second_confirmation(monkeypatch):
    conn = PGFixture()
    class Engine:
        @contextmanager
        def begin(self):
            yield conn
    monkeypatch.setattr(catalog_routes, "engine", Engine())
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {
        "ed2_manual_barcodes", "external_article_product_links", "global_products",
    })
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda _: SimpleNamespace(user_id="frontteam-1"))
    monkeypatch.setattr(catalog_routes, "resolve_external_article_identity",
                        lambda _conn, receipt_id: {
                            "retailer_code": "AH", "receipt_text": "Courgette",
                            "external_article_code": "21003",
                        })
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("OFF must not be called")
                        ))
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin="8722800072026",
        )
    )
    assert result["saved"] is True and result["catalog_linked"] is True
    assert result["catalog_product_created"] is True
    assert len(conn.products) == 1 and len(conn.manual) == 1


def test_historical_bulk_uses_existing_proof_without_off(monkeypatch):
    conn = PGFixture()
    conn.manual.extend([
        {"retailer_code": "ah", "receipt_text_normalized": "courgette",
         "external_article_code": "21003", "gtin": "8722800072026",
         "barcode_scope": None, "global_product_id": None},
        {"retailer_code": "jumbo", "receipt_text_normalized": "jumbo courgette",
         "external_article_code": "99001", "gtin": "8722800072026",
         "barcode_scope": None, "global_product_id": None},
    ])

    class Engine:
        @contextmanager
        def begin(self):
            yield conn

    monkeypatch.setattr(catalog_routes, "engine", Engine())
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {
        "ed2_manual_barcodes", "external_article_product_links",
        "global_products", "product_identities",
    })
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda permission: SimpleNamespace(user_id="authorized-frontteam"))
    sources = {
        "r1": {"retailer_code": "AH", "receipt_text": "Courgette",
               "external_article_code": "21003"},
        "r2": {"retailer_code": "Jumbo", "receipt_text": "Jumbo courgette",
               "external_article_code": "99001"},
    }
    monkeypatch.setattr(catalog_routes, "resolve_external_article_identity",
                        lambda _conn, receipt_id: sources[receipt_id])
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("No OFF lookup permitted")))
    result = catalog_routes.materialize_existing_ed2_manual_barcodes(
        catalog_routes.Ed2HistoricalBarcodesRequest(selections=[
            catalog_routes.Ed2HistoricalBarcodeSelection(
                receipt_item_id="r1", gtin="8722800072026"),
            catalog_routes.Ed2HistoricalBarcodeSelection(
                receipt_item_id="r2", gtin="8722800072026"),
        ])
    )
    assert result == {
        "ok": True, "processed": 2, "catalog_links_created": 2,
        "already_confirmed": 0, "catalog_products_created": 1,
        "household_changes": 0, "stock_changes": 0,
    }
    assert len(conn.products) == 1 and len(conn.manual) == 2
    assert all(row["global_product_id"] == conn.products[0]["id"] for row in conn.manual)
    assert set(conn.writes) <= {
        "global_products", "product_identities", "ed2_manual_barcodes",
    }
    before = len(conn.writes)
    second = catalog_routes.materialize_existing_ed2_manual_barcodes(
        catalog_routes.Ed2HistoricalBarcodesRequest(selections=[
            catalog_routes.Ed2HistoricalBarcodeSelection(
                receipt_item_id="r1", gtin="8722800072026"),
        ])
    )
    assert second["already_confirmed"] == 1
    assert len(conn.writes) == before


def test_historical_bulk_rejects_missing_proof_and_changed_gtin(monkeypatch):
    conn = PGFixture()
    conn.manual.append({
        "retailer_code": "ah", "receipt_text_normalized": "courgette",
        "external_article_code": "21003", "gtin": "8722800072026",
        "barcode_scope": None, "global_product_id": None,
    })

    class Engine:
        @contextmanager
        def begin(self):
            yield conn

    monkeypatch.setattr(catalog_routes, "engine", Engine())
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {
        "ed2_manual_barcodes", "external_article_product_links",
        "global_products", "product_identities",
    })
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda _permission: SimpleNamespace(user_id="frontteam-1"))
    monkeypatch.setattr(catalog_routes, "resolve_external_article_identity",
                        lambda _conn, receipt_id: {
                            "retailer_code": "AH", "receipt_text": "Courgette",
                            "external_article_code": "21003" if receipt_id == "r1" else "missing",
                        })
    for receipt_id, barcode in [
        ("r1", _barcode("871234567890")),
        ("missing", "8722800072026"),
    ]:
        with pytest.raises(catalog_routes.HTTPException) as exc:
            catalog_routes.materialize_existing_ed2_manual_barcodes(
                catalog_routes.Ed2HistoricalBarcodesRequest(selections=[
                    catalog_routes.Ed2HistoricalBarcodeSelection(
                        receipt_item_id=receipt_id, gtin=barcode),
                ])
            )
        assert exc.value.status_code == 409
    assert not conn.writes


def test_historical_bulk_selection_bound_and_duplicates():
    with pytest.raises(ValueError):
        catalog_routes.Ed2HistoricalBarcodesRequest(selections=[])
    with pytest.raises(ValueError):
        catalog_routes.Ed2HistoricalBarcodesRequest(selections=[
            catalog_routes.Ed2HistoricalBarcodeSelection(
                receipt_item_id="same", gtin="8722800072026"),
            catalog_routes.Ed2HistoricalBarcodeSelection(
                receipt_item_id="same", gtin="8722800072026"),
        ])



def test_soft_deleted_lidl_global_identity_is_not_resurrected():
    """Deleting in Catalogus is soft-delete, not proof that GTIN is free."""
    conn = PGFixture()
    conn.products.append({
        "id": "deleted-lidl-product", "status": "deleted",
        "primary_gtin": "2008234600001", "name": "Lidl oud artikel",
    })
    with pytest.raises(ValueError, match="historisch als mondiale code"):
        save(conn, retailer="Lidl", label="Lidl artikel", number="723",
             barcode="2008234600001")
    assert conn.writes == []
    assert conn.products[0]["status"] == "deleted"


def test_soft_deleted_global_gtin_stays_unavailable_for_reidentification():
    conn = PGFixture()
    conn.products.append({
        "id": "deleted-global-product", "status": "deleted",
        "primary_gtin": "8722800072026", "name": "Oud artikel",
    })
    with pytest.raises(ValueError, match="niet actief"):
        save(conn, retailer="AH", label="Courgette", number="21003",
             barcode="8722800072026")
    assert not conn.writes


def test_soft_deleted_lidl_manual_link_is_not_silently_reactivated():
    conn = PGFixture()
    conn.products.append({
        "id": "deleted-lidl-product", "status": "deleted",
        "primary_gtin": None, "name": "Oud Lidl artikel",
    })
    conn.manual.append({
        "retailer_code": "lidl", "receipt_text_normalized": "lidl artikel",
        "external_article_code": "723", "gtin": "2008234600001",
        "barcode_scope": "restricted",
        "global_product_id": "deleted-lidl-product",
    })
    with pytest.raises(ValueError, match="niet langer actief"):
        save(conn, retailer="Lidl", label="Lidl artikel", number="723",
             barcode="2008234600001")
    assert not conn.writes
    assert conn.manual[0]["global_product_id"] == "deleted-lidl-product"



def test_deleted_lidl_gtin_identity_without_primary_barcode_is_not_reused():
    """A deleted product may still own a global GTIN identity row."""
    conn = PGFixture()
    conn.products.append({
        "id": "deleted-lidl-identity", "status": "deleted",
        "primary_gtin": None, "name": "Lidl artikel met oude barcode",
    })
    conn.identities.append({
        "global_product_id": "deleted-lidl-identity",
        "identity_type": "gtin", "identity_value": "2008234600001",
    })
    with pytest.raises(ValueError, match="historisch als mondiale code"):
        save(conn, retailer="Lidl", label="Lidl artikel", number="723",
             barcode="2008234600001")
    assert conn.writes == []
    assert len(conn.products) == 1
