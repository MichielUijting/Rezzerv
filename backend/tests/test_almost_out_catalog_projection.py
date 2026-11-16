"""Bijna op Catalogus presentation: verified only, zero household writes."""
from __future__ import annotations

from app.services import almost_out_catalog_projection as module


def _article(id_, *, product_id=None, name="Huishoudnaam", image=""):
    return {
        "id": id_, "household_id": "household-a", "naam": name,
        "global_product_id": product_id, "image_url": image,
    }


def _signal(id_, *, members=None, image="", name="Huishoudnaam"):
    return {
        "household_article_id": id_, "member_article_ids": members or [],
        "household_article_name": name, "product_name": name,
        "image_url": image, "current_quantity": 3, "amount_to_buy": 2,
        "gpc_brick_name": "",
    }


def _stub_product_queries(monkeypatch, products, classifications=None):
    monkeypatch.setattr(module, "_active_catalog_products",
                        lambda _conn, ids: {
                            pid: value for pid, value in products.items() if pid in ids
                        })
    monkeypatch.setattr(module, "_confirmed_catalog_gpc",
                        lambda _conn, ids: {
                            pid: value for pid, value in (classifications or {}).items() if pid in ids
                        })


def test_confirmed_receipt_match_projects_catalog_name_photo_and_gpc_without_changing_stock(monkeypatch):
    def exact_receipt_link(_conn, _text, rows, *, verified_identity_by_article):
        assert [row["id"] for row in rows] == ["gouda-household"]
        verified_identity_by_article["gouda-household"] = "catalog-gouda"
        return {"gouda-household": "https://images.example/gouda.jpg"}

    monkeypatch.setattr(module, "resolve_household_catalog_images", exact_receipt_link)
    _stub_product_queries(monkeypatch, {
        "catalog-gouda": {"id": "catalog-gouda", "name": "Gouda Belegen 48+",
                          "image_url": "https://images.example/gouda.jpg"},
    }, {
        "catalog-gouda": {"gpc_brick_code": "10000215",
                          "gpc_brick_name": "Kaas", "gpc_class_name": "Kaasproducten",
                          "gpc_family_name": "Zuivel"},
    })
    row = _signal("gouda-household", name="Gouda belegen gerasp")
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("gouda-household", name="Gouda belegen gerasp"),
    ], [row])
    assert row["household_article_id"] == "gouda-household"
    assert row["household_article_name"] == "Gouda belegen gerasp"
    assert row["product_name"] == "Gouda Belegen 48+"
    assert row["image_url"] == "https://images.example/gouda.jpg"
    assert row["gpc_brick_name"] == "Kaas"
    assert row["catalog_product_id"] == "catalog-gouda"
    assert row["photo_missing_reason"] is None
    assert row["current_quantity"] == 3
    assert row["amount_to_buy"] == 2


def test_unproved_receipt_link_never_renames_on_name_or_photo(monkeypatch):
    # The legacy image resolver can find a one-name photo; that does not prove
    # a household-to-Catalogus link for product name or GS1 inheritance.
    def legacy_name_photo(_conn, _text, _rows, *, verified_identity_by_article):
        assert not verified_identity_by_article
        return {"no-identity": "https://images.example/legacy.jpg"}
    monkeypatch.setattr(module, "resolve_household_catalog_images", legacy_name_photo)
    _stub_product_queries(monkeypatch, {})
    row = _signal("no-identity", name="Goudsalami")
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("no-identity", name="Goudsalami"),
    ], [row])
    assert row["product_name"] == "Goudsalami"
    assert row.get("catalog_product_id") is None
    assert row["image_url"].endswith("legacy.jpg")
    assert row["photo_missing_reason"] is None


def test_unidentified_article_without_photo_explains_missing_catalog_link(monkeypatch):
    monkeypatch.setattr(module, "resolve_household_catalog_images",
                        lambda _conn, _text, _rows, *, verified_identity_by_article: {})
    _stub_product_queries(monkeypatch, {})
    row = _signal("unknown", name="Pays doc Merlot BiB")
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("unknown", name="Pays doc Merlot BiB"),
    ], [row])
    assert row["photo_missing_reason"] == "Geen bevestigde Cataloguskoppeling"
    assert not row["image_url"]
    assert row["household_article_name"] == row["product_name"]


def test_proven_product_without_photo_explains_actual_absence(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("Direct Catalogus link needs no receipt/image identity lookup")
    monkeypatch.setattr(module, "resolve_household_catalog_images", fail)
    _stub_product_queries(monkeypatch, {
        "catalog-beet": {"id": "catalog-beet", "name": "Rode bieten gekookt", "image_url": ""},
    })
    row = _signal("beet")
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("beet", product_id="catalog-beet"),
    ], [row])
    assert row["product_name"] == "Rode bieten gekookt"
    assert row["photo_missing_reason"] == "Catalogus heeft geen foto"
    assert row["image_url"] == ""


def test_verified_member_presents_catalog_only_with_existing_group_membership(monkeypatch):
    def resolver(_conn, _text, rows, *, verified_identity_by_article):
        assert {row["id"] for row in rows} == {"representative", "related"}
        verified_identity_by_article["related"] = "catalog-variant"
        return {}
    monkeypatch.setattr(module, "resolve_household_catalog_images", resolver)
    _stub_product_queries(monkeypatch, {
        "catalog-variant": {"id": "catalog-variant", "name": "Basmati Langkorrelige Rijst",
                            "image_url": "https://images.example/basmati.jpg"},
    })
    row = _signal("representative", members=["representative", "related"])
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("representative"), _article("related"),
    ], [row])
    assert row["household_article_id"] == "representative"
    assert row["product_name"] == "Basmati Langkorrelige Rijst"
    assert row["image_url"].endswith("basmati.jpg")


def test_own_confirmed_product_wins_over_other_member(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("No unresolved household articles")
    monkeypatch.setattr(module, "resolve_household_catalog_images", fail)
    _stub_product_queries(monkeypatch, {
        "catalog-own": {"id": "catalog-own", "name": "Eigen product", "image_url": "own.jpg"},
        "catalog-peer": {"id": "catalog-peer", "name": "Synoniemproduct", "image_url": "peer.jpg"},
    })
    row = _signal("own", members=["own", "peer"])
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("own", product_id="catalog-own"),
        _article("peer", product_id="catalog-peer"),
    ], [row])
    assert row["product_name"] == "Eigen product"
    assert row["image_url"] == "own.jpg"


def test_malformed_or_conflicting_product_evidence_stays_untouched(monkeypatch):
    def conflict(_conn, _text, _rows, *, verified_identity_by_article):
        return {}
    monkeypatch.setattr(module, "resolve_household_catalog_images", conflict)
    _stub_product_queries(monkeypatch, {})
    row = _signal("ambiguous", name="Goudsalami")
    module.fill_visible_almost_out_catalog_details(object(), object(), [
        _article("ambiguous", name="Goudsalami"),
        _article("other-household", product_id="catalog-foreign", image="foreign.jpg"),
    ], [row])
    assert row["image_url"] == ""
    assert row["product_name"] == "Goudsalami"
    assert row["photo_missing_reason"] == "Geen bevestigde Cataloguskoppeling"
    assert row.get("catalog_product_id") is None


def test_no_visible_signals_is_a_noop():
    assert module.fill_visible_almost_out_catalog_details(
        object(), object(), [_article("a", product_id="catalog-a")], [],
    ) == []
