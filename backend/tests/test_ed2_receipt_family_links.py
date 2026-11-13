"""Barcode-free curator-approved courgette source: independent of GTIN/GPC.

All assertions use mocked read-only candidates. Database writes and access
control are separately enforced in PostgreSQL/route contracts.
"""
from types import SimpleNamespace
import pytest

from app.services import ed2_receipt_family_link_service as family


SOURCE = {
    "retailer_code": "Lidl", "receipt_text": "Courgette groen",
    "external_article_code": "0082346",
}
BASE = {"id": "catalog-ah", "name": "AH Courgette",
        "primary_gtin": "8722800072026", "variant": ""}


@pytest.mark.parametrize("label,expected", [
    ("Courgette", "standard"),
    ("Courgette groen", "standard"),
    ("COURGETTES", "standard"),
    ("Courgette geel", "yellow"),
    ("Courgette Bio", "organic"),
    ("Olvarit 8+ Maanden Courgette", ""),
    ("Diepvries courgette", ""),
    ("Courgettesoep", ""),
    ("Courgette maaltijdmix", ""),
    ("Courgette 2 stuks", ""),
])
def test_only_curated_fresh_courgette_is_eligible(label, expected):
    assert family._family_variant(label.lower()) == expected


def test_exact_source_tuple_is_not_a_fake_barcode():
    assert family._parts(SOURCE) == ("lidl", "courgette groen", "0082346")
    assert family._matching_target("standard", BASE) == "same_product"
    assert family._matching_target("yellow", BASE) == "synonym_variant"
    assert family._matching_target("organic", BASE) == "synonym_variant"
    assert family._matching_target("standard", {"name": "Courgette geel"}) is None


def test_read_only_options_do_not_write(monkeypatch):
    seen = []
    monkeypatch.setattr(family, "load_products", lambda conn: [
        BASE, {"id": "bad", "name": "Olvarit 8+ Maanden Courgette"},
        {"id": "frozen", "name": "Diepvries courgette"},
    ])
    source = {**SOURCE, "receipt_text": "Courgette geel"}
    response = family.family_options(SimpleNamespace(), source)
    assert response["family"] == "verse_courgette_v1"
    assert [(x["product_id"], x["mode"]) for x in response["options"]] == [
        ("catalog-ah", "synonym_variant")
    ]
    assert len(response["options"][0]["fingerprint"]) == 64


def test_confirmation_rejects_non_postgresql_before_accessing_any_data():
    with pytest.raises(ValueError, match="PostgreSQL"):
        family.confirm_courgette_receipt(
            SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
            source=SOURCE, receipt_item_id="receipt-table-line:1",
            target_product_id="catalog-ah", match_mode="same_product",
            expected_fingerprint="0" * 64, actor_id="frontteam-user",
        )


def test_confirmation_requires_explicit_current_option(monkeypatch):
    calls = []
    class Conn:
        dialect = SimpleNamespace(name="postgresql")
        def execute(self, statement, params=None):
            sql = str(statement)
            calls.append(sql)
            assert "pg_advisory_xact_lock" in sql
            return SimpleNamespace()
    monkeypatch.setattr(family, "family_options", lambda conn, source: {
        "options": [{"product_id": "catalog-ah", "mode": "same_product",
                     "fingerprint": "1" * 64}]
    })
    with pytest.raises(ValueError, match="gewijzigd"):
        family.confirm_courgette_receipt(
            Conn(), source=SOURCE, receipt_item_id="receipt-table-line:1",
            target_product_id="catalog-ah", match_mode="same_product",
            expected_fingerprint="0" * 64, actor_id="frontteam-user",
        )
    assert all("pg_advisory_xact_lock" in stmt for stmt in calls)


def test_source_key_does_not_merge_retailers_or_codes():
    other = {**SOURCE, "retailer_code": "Jumbo"}
    blank = {**SOURCE, "external_article_code": ""}
    assert family._parts(SOURCE) != family._parts(other)
    assert family._parts(SOURCE) != family._parts(blank)
    assert family._snapshot(SOURCE, BASE, "same_product") != family._snapshot(other, BASE, "same_product")


def test_existing_manual_barcode_prevents_barcode_free_claim():
    class Query:
        def first(self): return ("2008234600001",)
    class Conn:
        def execute(self, statement, values):
            assert "FROM ed2_manual_barcodes" in str(statement)
            return Query()
    with pytest.raises(ValueError, match="bewaarde barcode"):
        family._guard_preexisting_claims(Conn(), SOURCE)


def test_existing_conflicting_catalog_link_prevents_replacement():
    class Query:
        def __init__(self, rows): self.rows = rows
        def first(self): return self.rows[0] if self.rows else None
        def scalars(self): return self
        def all(self): return self.rows
    class Conn:
        def execute(self, statement, values):
            sql = str(statement)
            if "ed2_manual_barcodes" in sql: return Query([])
            if "external_article_product_links" in sql: return Query(["catalog-other"])
            raise AssertionError(sql)
    with pytest.raises(ValueError, match="andere Catalogusidentiteit"):
        family._guard_preexisting_claims(Conn(), SOURCE)


def test_confirm_same_product_is_explicit_and_idempotent(monkeypatch):
    writes, audits = [], []
    params = family._parts(SOURCE)
    fingerprint = "a" * 64

    class Query:
        def __init__(self, rows=()): self.rows = list(rows)
        def mappings(self): return self
        def first(self): return self.rows[0] if self.rows else None

    class Conn:
        dialect = SimpleNamespace(name="postgresql")
        def execute(self, statement, values=None):
            sql = " ".join(str(statement).split())
            if "pg_advisory_xact_lock" in sql: return Query()
            if sql.startswith("SELECT global_product_id, match_mode FROM ed2_receipt_family_links"):
                return Query([{"global_product_id": "catalog-ah",
                               "match_mode": "same_product"}] if writes else [])
            if sql.startswith("INSERT INTO ed2_receipt_family_links"):
                writes.append(dict(values))
                return Query()
            raise AssertionError("Unexpected SQL: " + sql)

    monkeypatch.setattr(family, "family_options", lambda _conn, _source: {
        "options": [{"product_id": "catalog-ah", "mode": "same_product",
                     "fingerprint": fingerprint}]})
    monkeypatch.setattr(family, "_guard_preexisting_claims", lambda _conn, _source: None)
    monkeypatch.setattr(family, "write_authorization_audit",
                        lambda *a, **kw: audits.append(kw))
    kwargs = dict(source=SOURCE, receipt_item_id="receipt-table-line:green",
                  target_product_id="catalog-ah", match_mode="same_product",
                  expected_fingerprint=fingerprint, actor_id="frontteam-authorized")
    result = family.confirm_courgette_receipt(Conn(), **kwargs)
    assert result["ok"] and not result["barcode_written"]
    assert result["global_product_id"] == "catalog-ah"
    assert writes == [{
        "retailer": "lidl", "label": "courgette groen", "code": "0082346",
        "product": "catalog-ah", "mode": "same_product", "actor": "frontteam-authorized",
    }]
    assert len(audits) == 1
    assert audits[0]["actor_user_id"] == "frontteam-authorized"
    duplicate = family.confirm_courgette_receipt(Conn(), **kwargs)
    assert duplicate["already_confirmed"]
    assert len(writes) == 1 and len(audits) == 1


def test_repeated_yellow_confirmation_uses_direct_synonym_proof(monkeypatch):
    fingerprint = "b" * 64
    class Query:
        def __init__(self, rows): self.rows = rows
        def mappings(self): return self
        def first(self): return self.rows[0] if self.rows else None
    class Conn:
        dialect = SimpleNamespace(name="postgresql")
        def execute(self, statement, values=None):
            sql = " ".join(str(statement).split())
            if "pg_advisory_xact_lock" in sql: return Query([])
            if sql.startswith("SELECT global_product_id, match_mode FROM ed2_receipt_family_links"):
                return Query([{"global_product_id": "catalog-yellow",
                               "match_mode": "synonym_variant"}])
            if "FROM article_synonym_links" in sql: return Query([(1,)])
            raise AssertionError("No mutation allowed on retry: " + sql)
    monkeypatch.setattr(family, "family_options", lambda _conn, _source: {
        "options": [{"product_id": "catalog-ah", "mode": "synonym_variant",
                     "fingerprint": fingerprint}]})
    result = family.confirm_courgette_receipt(
        Conn(), source={**SOURCE, "receipt_text": "Courgette geel"},
        receipt_item_id="receipt-table-line:yellow", target_product_id="catalog-ah",
        match_mode="synonym_variant", expected_fingerprint=fingerprint,
        actor_id="frontteam-authorized")
    assert result["already_confirmed"]
    assert result["global_product_id"] == "catalog-yellow"
    assert not result["barcode_written"]


def test_confirm_route_rejects_operator_without_platform_authorization(monkeypatch):
    from app.api import catalog_routes
    from fastapi import HTTPException
    payload = catalog_routes.Ed2CourgetteFamilyConfirmation(
        receipt_item_id="receipt-table-line:green",
        target_product_id="catalog-ah", match_mode="same_product",
        fingerprint="a" * 64,
    )
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda permission: SimpleNamespace(
                            user_id="unprivileged", is_platform_superuser=False,
                            is_frontteam=False))
    class NoWriteEngine:
        def begin(self):
            raise AssertionError("Database write transaction must not start")
    monkeypatch.setattr(catalog_routes, "engine", NoWriteEngine())
    with pytest.raises(HTTPException) as error:
        catalog_routes.confirm_ed2_courgette_family(payload)
    assert error.value.status_code == 403


def test_confirm_route_rechecks_source_server_side_not_browser_claim(monkeypatch):
    from app.api import catalog_routes

    payload = catalog_routes.Ed2CourgetteFamilyConfirmation(
        receipt_item_id="receipt-table-line:green",
        target_product_id="catalog-ah", match_mode="same_product",
        fingerprint="a" * 64,
    )
    class ManagedTransaction:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(catalog_routes, "engine", SimpleNamespace(
        begin=lambda: ManagedTransaction()))
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda permission: SimpleNamespace(
                            user_id="frontteam-allowed", is_platform_superuser=False,
                            is_frontteam=True))
    sources = []
    def source_resolver(conn, item_id):
        sources.append(item_id)
        return SOURCE
    monkeypatch.setattr(catalog_routes, "resolve_external_article_identity", source_resolver)
    recorded = []
    def confirmation(conn, **kwargs):
        recorded.append(kwargs)
        return {"ok": True, "global_product_id": "catalog-ah",
                "barcode_written": False, "synonym_created": False}
    monkeypatch.setattr(catalog_routes, "confirm_courgette_receipt", confirmation)
    outcome = catalog_routes.confirm_ed2_courgette_family(payload)
    assert outcome["ok"] and outcome["barcode_written"] is False
    assert sources == [payload.receipt_item_id]
    assert recorded[0]["source"] == SOURCE
    assert recorded[0]["actor_id"] == "frontteam-allowed"
    assert recorded[0]["expected_fingerprint"] == payload.fingerprint


def test_confirm_route_rejects_invalid_fingerprint_before_write(monkeypatch):
    from app.api import catalog_routes
    from fastapi import HTTPException
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda permission: SimpleNamespace(
                            user_id="superuser", is_platform_superuser=True,
                            is_frontteam=False))
    class NoWriteEngine:
        def begin(self):
            raise AssertionError("Unexpected DB write")
    monkeypatch.setattr(catalog_routes, "engine", NoWriteEngine())
    payload = catalog_routes.Ed2CourgetteFamilyConfirmation(
        receipt_item_id="receipt-table-line:green", target_product_id="catalog-ah",
        match_mode="same_product", fingerprint="not-a-sha256",
    )
    with pytest.raises(HTTPException) as error:
        catalog_routes.confirm_ed2_courgette_family(payload)
    assert error.value.status_code == 422



@pytest.mark.parametrize("retailer,name,article_code,expected", [
    ("Albert Heijn", "COURGETTE", "21003", "same_product"),
    ("Albert Heijn", "COURGETTE", "", "same_product"),
    ("Jumbo", "COURGETTE", "", "same_product"),
    ("Lidl", "Courgette Bio", "0084544", "synonym_variant"),
    ("Lidl", "Courgette geel", "0082293", "synonym_variant"),
    ("Lidl", "Courgette groen", "0082346", "same_product"),
    ("Lidl", "Courgette groen", "", "same_product"),
])
def test_seven_courgette_acceptance_rows_are_only_suggestions(
        monkeypatch, retailer, name, article_code, expected):
    """The PO's seven receipt cases: never fabricate or write an EAN."""
    captured = []
    monkeypatch.setattr(family, "load_products", lambda conn: [BASE])
    source = {"retailer_code": retailer, "receipt_text": name,
              "external_article_code": article_code}
    class ReadOnly:
        def execute(self, statement, params=None):
            captured.append(str(statement))
            raise AssertionError("A family suggestion may not write or query receipts")
    result = family.family_options(ReadOnly(), source)
    assert result["family"] == "verse_courgette_v1"
    assert len(result["options"]) == 1
    option = result["options"][0]
    assert option["mode"] == expected
    assert option["product_id"] == "catalog-ah"
    assert option["barcode"] == BASE["primary_gtin"]
    assert captured == []


@pytest.mark.parametrize("receipt", [
    "Olvarit 8+ Maanden Courgette",
    "Diepvries courgette", "Courgettesoep", "Courgette maaltijdmix",
])
def test_olvarit_frozen_and_prepared_not_even_suggested(monkeypatch, receipt):
    monkeypatch.setattr(family, "load_products", lambda conn: [BASE])
    source = {"retailer_code": "Lidl", "receipt_text": receipt,
              "external_article_code": ""}
    result = family.family_options(SimpleNamespace(), source)
    assert result["family"] is None
    assert result["options"] == []
