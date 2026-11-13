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
