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
                      "off_found": False, "off_unavailable": False,
                      "classification_pending": False, "photo_loaded": False}
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

def test_off_unavailable_preserves_barcode_only_without_claiming_off_match(guard):
    conn, _, _, linked, monkeypatch = guard
    from app.services.off_search_service import OffUnavailableError
    code = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: (_ for _ in ()).throw(
                            OffUnavailableError("Open Food Facts is tijdelijk niet bereikbaar. Probeer opnieuw.")
                        ))
    result = save(code)
    assert result["saved"] is True
    assert result["off_found"] is False
    assert result["off_unavailable"] is True
    assert result["source"] == "manual"
    assert conn.manual == {("jumbo", "melk", "123"): code}
    assert not linked
    assert conn.inventory_events == [{"id": "e1"}]
    assert conn.household_articles == [{"id": "h1", "stock": 4}]


def test_non_outage_off_search_error_must_not_save(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    from app.services.off_search_service import OffSearchError
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: (_ for _ in ()).throw(
                            OffSearchError("Bonartikel niet gevonden")
                        ))
    with pytest.raises(HTTPException) as error:
        save(valid_gtin())
    assert error.value.status_code == 422
    assert conn.manual == {}
    assert not linked


def test_retry_after_outage_enriches_existing_barcode_when_off_recovers(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    from app.services.off_search_service import OffUnavailableError
    code = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates",
                        lambda payload: (_ for _ in ()).throw(
                            OffUnavailableError("OFF unavailable")
                        ))
    assert save(code)["off_unavailable"] is True
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": code, "selection_proof": "server-proof",
                     "identity_compatible": True, "image_url": "https://example.test/photo.jpg"}],
    })
    assert save(code)["off_found"] is True
    assert linked and linked[0]["selection_proof"] == "server-proof"


def test_explicit_off_mismatch_override_saves_only_manual_barcode(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    code = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": code, "identity_compatible": False,
                     "selection_proof": "must-not-be-used", "image_url": "https://example.test/other.jpg"}],
    })
    result = catalog_routes.save_ed2_manual_barcode(
        catalog_routes.Ed2ManualBarcodeRequest(
            receipt_item_id="receipt-table-line:r1", gtin=code, allow_off_mismatch=True,
        )
    )
    assert result["saved"] is True and result["source"] == "manual"
    assert not result["off_found"] and not result["photo_loaded"]
    assert not linked
    assert conn.manual == {("jumbo", "melk", "123"): code}
    assert conn.household_articles == [{"id": "h1", "stock": 4}]
    assert conn.receipt_lines == [{"id": "r1", "label": "Melk"}]


def test_mismatch_returns_off_product_name_and_exact_barcode(guard, monkeypatch):
    conn, _, _, linked, _ = guard
    code = valid_gtin()
    monkeypatch.setattr(catalog_routes, "search_off_candidates", lambda payload: {
        "results": [{"gtin": code, "product_name": "Ander merk Amsterdamse uien",
                     "brand": "Voorbeeldmerk", "quantity": "320 g",
                     "identity_compatible": False,
                     "identity_conflict_message": "Huismerk wijkt af",
                     "selection_proof": "unused"}],
    })
    with pytest.raises(HTTPException) as exc:
        save(code)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["code"] == "off_identity_mismatch"
    assert detail["product_name"] == "Ander merk Amsterdamse uien"
    assert detail["gtin"] == code
    assert detail["quantity"] == "320 g"
    assert detail["conflict_reason"] == "Huismerk wijkt af"
    assert conn.manual == {}
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
    with pytest.raises(HTTPException) as exc:
        save(gtin)
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
    with pytest.raises(HTTPException) as exc:
        save(gtin)
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
