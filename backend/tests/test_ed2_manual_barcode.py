"""Saved barcode is authoritative identification with no receipt/stock writes."""
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
                        lambda key: (permissions.append(key), SimpleNamespace(user_id="frontteam-1"))[1])
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
    def materialize(conn, *, retailer_code, receipt_text, external_article_code,
                    barcode, confirmed_by):
        assert confirmed_by == "frontteam-1"
        key = ("jumbo", "melk", "123")
        if conn.active:
            raise ValueError("Tegenstrijdige bestaande Cataloguskoppeling")
        existing = conn.manual.get(key)
        if existing and existing != barcode:
            raise ValueError("Dit bonartikel heeft een andere opgeslagen barcode")
        conn.manual[key] = barcode
        return {
            "status": "already_confirmed" if existing else "confirmed",
            "barcode_scope": "global_candidate", "catalog_product_created": not existing,
            "global_product_id": "product-1",
        }
    monkeypatch.setattr(catalog_routes, "materialize_saved_ed2_barcode", materialize)
    return engine.conn, permissions, search_calls, linked, monkeypatch


def save(code):
    return catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=code,
        )
    )


def test_saved_barcode_is_confirmed_catalog_identity_without_off(guard):
    conn, permissions, search_calls, linked, _ = guard
    before_household = [dict(x) for x in conn.household_articles]
    before_receipt = [dict(x) for x in conn.receipt_lines]
    before_events = [dict(x) for x in conn.inventory_events]
    code = valid_gtin()
    result = save(code)
    assert result["saved"] is True
    assert result["catalog_linked"] is True
    assert result["catalog_product_created"] is True
    assert result["global_product_id"] == "product-1"
    assert permissions == ["platform.external_products.link_existing"]
    assert not search_calls and not linked
    assert conn.manual == {("jumbo", "melk", "123"): code}
    assert conn.household_articles == before_household
    assert conn.receipt_lines == before_receipt
    assert conn.inventory_events == before_events
    assert save(code)["catalog_product_created"] is False


@pytest.mark.parametrize("error_case", ["bad_checksum", "collision", "active_link"])
def test_invalid_or_conflicting_saved_barcode_never_changes_data(guard, error_case):
    conn, _, _, linked, _ = guard
    code = valid_gtin()
    if error_case == "bad_checksum":
        code = code[:-1] + str((int(code[-1]) + 1) % 10)
    elif error_case == "collision":
        conn.manual[("jumbo", "melk", "123")] = valid_gtin("871234567891")
    else:
        conn.active = True
    old = dict(conn.manual)
    with pytest.raises(HTTPException) as exc:
        save(code)
    assert exc.value.status_code == (422 if error_case == "bad_checksum" else 409)
    assert conn.manual == old
    assert not linked


def test_permission_required_before_catalog_mutation(guard, monkeypatch):
    conn, _, _, _, _ = guard
    def deny(key):
        assert key == "platform.external_products.link_existing"
        raise HTTPException(status_code=403, detail="denied")
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", deny)
    with pytest.raises(HTTPException) as err:
        save(valid_gtin())
    assert err.value.status_code == 403
    assert not conn.manual and not conn.sql_log


def test_unknown_receipt_source_is_not_saved(guard):
    conn, _, _, _, _ = guard
    with pytest.raises(HTTPException) as err:
        catalog_routes.save_ed2_manual_barcode(catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:not-exists",
            gtin=valid_gtin(),
        ))
    assert err.value.status_code == 404
    assert not conn.manual


@pytest.mark.parametrize("failure", ["unavailable", "search_error", "mismatch"])
def test_off_outages_errors_and_mismatches_never_block_saved_identity(guard, monkeypatch, failure):
    conn, _, search_calls, linked, _ = guard
    from app.services.off_search_service import OffUnavailableError, OffSearchError
    def off(_payload):
        if failure == "unavailable":
            raise OffUnavailableError("OFF is offline")
        if failure == "search_error":
            raise OffSearchError("OFF search error")
        return {"results": [{"gtin": valid_gtin(), "identity_compatible": False}]}
    monkeypatch.setattr(catalog_routes, "search_off_candidates", off)
    result = save(valid_gtin())
    assert result["saved"] and result["catalog_linked"]
    assert not search_calls and not linked
    assert conn.manual == {("jumbo", "melk", "123"): valid_gtin()}


def test_repeated_manual_save_stays_idempotent_even_when_off_changes(guard, monkeypatch):
    conn, _, search_calls, linked, _ = guard
    code = valid_gtin()
    assert save(code)["catalog_product_created"] is True
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: (_ for _ in ()).throw(
                            AssertionError("OFF is not an identification authority")
                        ))
    assert save(code)["catalog_product_created"] is False
    assert conn.manual == {("jumbo", "melk", "123"): code}
    assert not search_calls and not linked


def test_user_saved_gtin_outweighs_incompatible_off_metadata(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: {"results": [{
                            "identity_compatible": False,
                            "product_name": "Ander product",
                        }]})
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1",
            gtin=valid_gtin(), allow_off_mismatch=True,
        ),
    )
    assert result["saved"] and result["catalog_linked"]
    assert conn.manual == {("jumbo", "melk", "123"): valid_gtin()}
    assert not linked


def test_unlinked_collision_uses_exact_receipt_number_when_present():
    from app.api.catalog_routes import _ed2_require_unlinked

    class QueryConnection:
        def __init__(self):
            self.sql = ""
            self.params = None
        def execute(self, statement, params):
            self.sql = str(statement)
            self.params = params
            return Result([])

    conn = QueryConnection()
    _ed2_require_unlinked(conn, {
        "retailer_code": "ah",
        "receipt_text_normalized": "ah bouillon",
        "external_article_code": "845556",
    })
    assert "external_article_code = :external_article_code" in conn.sql
    assert "receipt_text_normalized = :receipt_text_normalized" not in conn.sql
    assert conn.params["external_article_code"] == "845556"


def test_name_fallback_cannot_block_another_numbered_item():
    from app.api.catalog_routes import _ed2_require_unlinked

    class QueryConnection:
        def __init__(self):
            self.sql = ""
        def execute(self, statement, params):
            self.sql = str(statement)
            return Result([])

    conn = QueryConnection()
    _ed2_require_unlinked(conn, {
        "retailer_code": "ah",
        "receipt_text_normalized": "ah bouillon",
        "external_article_code": "",
    })
    assert "receipt_text_normalized = :receipt_text_normalized" in conn.sql
    assert "COALESCE(TRIM(external_article_code), '') = ''" in conn.sql


def test_receipt_bound_off_proof_mismatch_shows_override_without_saving(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    gtin = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{
            "gtin": gtin, "product_name": "Hertog Jan Pilsener",
            "brand": "Hertog Jan", "quantity": "330 ml",
            "identity_compatible": True, "selection_proof": "other-receipt",
        }],
    })
    def reject_proof(payload):
        raise ValueError("Dit zoekresultaat hoort niet bij het geselecteerde bonartikel.")
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", reject_proof)
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    with pytest.raises(HTTPException) as exc:
        catalog_routes.save_ed2_manual_barcode(catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=gtin,
            allow_off_mismatch=True, import_off_product_override=True,
        ))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "off_identity_mismatch"
    assert exc.value.detail["gtin"] == gtin
    assert exc.value.detail["product_name"] == "Hertog Jan Pilsener"
    assert conn.manual == {}
    assert not linked


def test_receipt_bound_off_proof_mismatch_superuser_override_saves_only_gtin(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    gtin = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{
            "gtin": gtin, "product_name": "Hertog Jan Pilsener",
            "identity_compatible": True, "selection_proof": "other-receipt",
        }],
    })
    def unexpected_confirm(payload):
        raise AssertionError("OFF confirmation must not run after explicit GTIN-only override")
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", unexpected_confirm)
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=gtin,
            allow_off_mismatch=True,
        ),
    )
    assert result["saved"] is True
    assert result["source"] == "manual"
    assert result["off_found"] is False
    assert result["photo_loaded"] is False
    assert conn.manual == {("jumbo", "melk", "123"): gtin}
    assert not linked


def test_unrelated_invalid_off_proof_still_fails_closed(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    gtin = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": gtin, "selection_proof": "expired", "identity_compatible": True}],
    })
    def invalid_proof(payload):
        raise ValueError("Het zoekresultaat is verlopen. Zoek opnieuw in OFF.")
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", invalid_proof)
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    with pytest.raises(HTTPException) as exc:
        catalog_routes.save_ed2_manual_barcode(catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=gtin,
            allow_off_mismatch=True, import_off_product_override=True,
        ))
    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, str)
    assert "verlopen" in exc.value.detail
    assert conn.manual == {}
    assert not linked


def test_superuser_import_override_confirms_complete_off_product(guard, monkeypatch):
    from app.services.off_manual_search_proof import verify_manual_off_proof
    conn, _, _, linked, _ = guard
    gtin = valid_gtin()
    off = {
        "gtin": gtin, "product_name": "Hertog Jan Pilsener",
        "brand": "Hertog Jan", "quantity": "330 ml", "category": "beer",
        "category_tags": ["en:beers"], "image_url": "https://example.test/off-photo.jpg",
        "identity_compatible": False, "selection_proof": "stale-other-receipt",
    }
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: {"results": [off]})
    def confirm(payload):
        saved = verify_manual_off_proof(payload["selection_proof"],
                                        receipt_item_id=payload["receipt_item_id"],
                                        gtin=payload["gtin"])
        assert saved["product_name"] == off["product_name"]
        assert saved["brand"] == off["brand"]
        assert saved["quantity"] == off["quantity"]
        assert saved["category"] == off["category"]
        assert saved["category_tags"] == off["category_tags"]
        assert saved["image_url"] == off["image_url"]
        assert payload["override_private_label_conflict"] is True
        linked.append(payload)
        return {"ok": True, "classification_pending": True}
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", confirm)
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=gtin,
            allow_off_mismatch=True, import_off_product_override=True,
        )
    )
    assert result["saved"] is True
    assert result["source"] == "off"
    assert result["off_found"] is True
    assert result["classification_pending"] is True
    assert result["photo_loaded"] is True
    assert conn.manual == {}
    assert len(linked) == 1


def test_import_off_override_denied_for_non_superuser(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=False))
    with pytest.raises(HTTPException) as exc:
        catalog_routes.save_ed2_manual_barcode(
            catalog_routes.Ed2ManualBarcodeRequest(
                receipt_item_id="receipt-table-line:r1", gtin=valid_gtin(),
                allow_off_mismatch=True, import_off_product_override=True,
            )
        )
    assert exc.value.status_code == 403
    assert conn.manual == {}
    assert not linked


def test_import_off_override_requires_explicit_mismatch_confirmation(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    with pytest.raises(HTTPException) as exc:
        catalog_routes.save_ed2_manual_barcode(
            catalog_routes.Ed2ManualBarcodeRequest(
                receipt_item_id="receipt-table-line:r1", gtin=valid_gtin(),
                import_off_product_override=True,
            )
        )
    assert exc.value.status_code == 403
    assert conn.manual == {}
    assert not linked


@pytest.mark.parametrize("csv_gtin,off_gtin", [
    ("08710956001151", "8710956001151"),
    ("08710400347927", "8710400347927"),
    ("08710400131465", "8710400131465"),
    ("08019873824530", "8019873824530"),
])
def test_leading_zero_gtin14_is_same_off_ean13_for_superuser_import(
    guard, monkeypatch, csv_gtin, off_gtin,
):
    from app.services.off_manual_search_proof import issue_manual_off_proof, verify_manual_off_proof
    conn, _, _, linked, _ = guard
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    def search(payload):
        assert payload["gtin"] == csv_gtin
        product = {
            "gtin": off_gtin, "product_name": "Correct OFF-product",
            "brand": "Merk", "quantity": "330 ml", "category": "drinks",
            "category_tags": ["en:drinks"], "image_url": "https://example.test/p.jpg",
            "identity_compatible": False,
        }
        product["selection_proof"] = issue_manual_off_proof(payload["receipt_item_id"], product)
        return {"results": [product]}
    monkeypatch.setattr(catalog_routes, "search_off_candidates", search)
    def confirm(payload):
        assert payload["gtin"] == off_gtin
        product = verify_manual_off_proof(
            payload["selection_proof"], receipt_item_id=payload["receipt_item_id"],
            gtin=payload["gtin"],
        )
        assert product["product_name"] == "Correct OFF-product"
        assert product["image_url"] == "https://example.test/p.jpg"
        assert payload["override_private_label_conflict"] is True
        linked.append(payload)
        return {"ok": True, "classification_pending": True}
    monkeypatch.setattr(catalog_routes, "confirm_selected_off_catalog_product", confirm)
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=csv_gtin,
            allow_off_mismatch=True, import_off_product_override=True,
        )
    )
    assert result["saved"] is True
    assert result["source"] == "off"
    assert result["off_found"] is True
    assert len(linked) == 1
    assert conn.manual == {}


def test_real_off_gtin_difference_remains_blocked_even_for_superuser(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    csv_gtin = "08710956001151"
    monkeypatch.setattr(catalog_routes, "resolve_current_server_session",
                        lambda: SimpleNamespace(is_platform_superuser=True))
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": "8710400131465", "product_name": "Andere EAN",
                     "identity_compatible": False, "selection_proof": "irrelevant"}],
    })
    with pytest.raises(HTTPException) as exc:
        catalog_routes.save_ed2_manual_barcode(
            catalog_routes.Ed2ManualBarcodeRequest(
                receipt_item_id="receipt-table-line:r1", gtin=csv_gtin,
                allow_off_mismatch=True, import_off_product_override=True,
            ),
        )
    assert exc.value.status_code == 409
    assert "OFF-barcode wijkt af" in exc.value.detail
    assert conn.manual == {}
    assert not linked
