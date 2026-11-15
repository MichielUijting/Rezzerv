"""Fail-closed Superuser ED2 barcode conflict correction contract.

The PostgreSQL-shaped fixture deliberately has no household, receipt mutation
or inventory write handlers. These tests never connect to a user database.
"""
from types import SimpleNamespace

import pytest

from app.services import ed2_barcode_conflict_resolution_service as service


SOURCE = {
    "retailer_code": "Albert Heijn",
    "receipt_text": "RISOTTORIJST",
    "external_article_code": "24827",
}
RECEIPT_ITEM = "receipt-table-line:risotto"
CATALOG_GTIN = "8712345678906"
MANUAL_GTIN = "8722800072026"
OTHER_GTIN = "8711111111111"


class Rows:
    def __init__(self, rows=(), rowcount=None):
        self.rows = list(rows)
        self.rowcount = len(self.rows) if rowcount is None else rowcount

    def mappings(self):
        return self

    def all(self):
        return [dict(row) for row in self.rows]


class Store:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.manual = [{
            "retailer_code": "ah", "receipt_text_normalized": "risottorijst",
            "external_article_code": "24827", "gtin": MANUAL_GTIN,
            "barcode_scope": "global_candidate", "global_product_id": "manual-product",
            "confirmed_by": "superuser", "confirmed_at": "2026-11-01",
            "updated_at": "2026-11-01",
        }]
        self.links = [{
            "id": "central-id", "retailer_code": "ah",
            "receipt_text_normalized": "risottorijst",
            "external_article_code": "24827", "global_product_id": "catalog-product",
            "status": "confirmed", "confirmed_by": "historical",
            "updated_at": "2026-11-01", "product_name": "Risotto",
            "primary_gtin": CATALOG_GTIN, "product_status": "active",
        }]
        self.product = {
            "id": "manual-product", "status": "active",
            "primary_gtin": MANUAL_GTIN,
        }
        self.writes = []
        self.locks = []

    def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        if sql.startswith("SELECT pg_advisory_xact_lock"):
            self.locks.append(p["key"])
            return Rows()
        if sql.startswith("SELECT retailer_code, receipt_text_normalized") and "FROM ed2_manual_barcodes" in sql:
            return Rows([row for row in self.manual
                         if row["retailer_code"] in p["aliases"]
                         and row["receipt_text_normalized"] == p["label"]
                         and row["external_article_code"] == p["code"]])
        if sql.startswith("SELECT link.id") and "FROM external_article_product_links link" in sql:
            return Rows([row for row in self.links
                         if row["retailer_code"] in p["aliases"]
                         and row["external_article_code"] == p["code"]
                         and row["status"] in ("confirmed", "classification_pending")])
        if sql.startswith("SELECT id, status, primary_gtin FROM global_products"):
            return Rows([self.product] if p["id"] == self.product["id"] else [])
        if sql.startswith("DELETE FROM ed2_manual_barcodes"):
            matched = [r for r in self.manual
                       if r["retailer_code"] == p["retailer"]
                       and r["gtin"] == p["old_gtin"]
                       and r["global_product_id"] == p["old_product"]]
            self.manual = [r for r in self.manual if r not in matched]
            self.writes.append("delete_manual")
            return Rows(rowcount=len(matched))
        if sql.startswith("UPDATE external_article_product_links"):
            matched = [r for r in self.links
                       if r["id"] == p["id"] and r["status"] == p["status"]
                       and r["global_product_id"] == p["product"]
                       and r["receipt_text_normalized"] == p["label"]]
            for r in matched:
                r["status"] = "inactive"
            self.writes.append("retire_exact_central")
            return Rows(rowcount=len(matched))
        if sql.startswith("UPDATE ed2_manual_barcodes"):
            matched = [r for r in self.manual
                       if r["retailer_code"] == p["retailer"]
                       and r["gtin"] == p["old_gtin"]
                       and r["global_product_id"] == p["old_product"]]
            for r in matched:
                r.update(gtin=p["new_gtin"], barcode_scope=None,
                         global_product_id=None, confirmed_by=None, confirmed_at=None)
            self.writes.append("replace_manual")
            return Rows(rowcount=len(matched))
        raise AssertionError("Unexpected SQL or household write: " + sql)


@pytest.fixture
def context(monkeypatch):
    conn = Store()
    events = []
    def fake_owner(_conn, *, barcode, retailer, label, code, scope):
        if barcode in (CATALOG_GTIN, MANUAL_GTIN, OTHER_GTIN):
            return "manual-product" if barcode == MANUAL_GTIN else "new-product", True
        return None, False

    def fake_materialize(_conn, *, barcode, **kwargs):
        events.append(("materialize", barcode))
        assert kwargs["require_existing"] is True
        if barcode == OTHER_GTIN:
            conn.manual[0].update(
                barcode_scope="global_candidate", global_product_id="new-product")
        return {"global_product_id": ("manual-product" if barcode == MANUAL_GTIN
                                      else "new-product")}

    def fake_audit(_conn, **kwargs):
        events.append(("audit", kwargs))
        assert kwargs["actor_type"] == "platform_user"
        assert kwargs["action"] == "catalog.ed2.barcode_conflict.resolved"
        return "audit-id"

    monkeypatch.setattr(service, "_owner", fake_owner)
    monkeypatch.setattr(service, "materialize_saved_ed2_barcode", fake_materialize)
    monkeypatch.setattr(service, "write_authorization_audit", fake_audit)
    return conn, events


def preview(conn, mode="keep_catalog", barcode=""):
    return service.preview_barcode_conflict_resolution(
        conn, source=SOURCE, receipt_item_id=RECEIPT_ITEM,
        mode=mode, new_gtin=barcode,
    )


def confirm(conn, proof, mode="keep_catalog", barcode="", actor="superuser-1"):
    return service.confirm_barcode_conflict_resolution(
        conn, source=SOURCE, receipt_item_id=RECEIPT_ITEM,
        mode=mode, new_gtin=barcode, preview_fingerprint=proof,
        actor_user_id=actor,
    )


def test_catalog_choice_previews_without_writing_then_removes_only_exact_manual_claim(context):
    conn, events = context
    prepared = preview(conn)
    assert prepared["can_confirm"]
    assert prepared["catalog_gtin"] == CATALOG_GTIN
    assert prepared["old_manual_gtin"] == MANUAL_GTIN
    assert not conn.writes and not events
    result = confirm(conn, prepared["preview_fingerprint"])
    assert result == {
        "corrected": True, "mode": "keep_catalog", "gtin": CATALOG_GTIN,
        "global_product_id": "catalog-product",
        "receipt_changes": 0, "household_changes": 0, "stock_changes": 0,
    }
    assert conn.manual == []
    assert conn.links[0]["status"] == "confirmed"
    assert conn.writes == ["delete_manual"]
    assert [e[0] for e in events] == ["audit"]
    assert conn.locks == sorted(conn.locks)
    with pytest.raises(ValueError, match="barcodegegevens|Correctie"):
        confirm(conn, prepared["preview_fingerprint"])


def test_manual_choice_retains_manual_product_and_only_retires_exact_central_link(context):
    conn, events = context
    prepared = preview(conn, "keep_manual")
    assert prepared["can_confirm"]
    result = confirm(conn, prepared["preview_fingerprint"], "keep_manual")
    assert result["gtin"] == MANUAL_GTIN
    assert result["global_product_id"] == "manual-product"
    assert conn.links[0]["status"] == "inactive"
    assert conn.manual[0]["gtin"] == MANUAL_GTIN
    assert conn.writes == ["retire_exact_central"]
    assert [e[0] for e in events] == ["materialize", "audit"]


def test_new_code_requires_checksum_and_explicit_confirmation(context):
    conn, events = context
    invalid = preview(conn, "use_other", "8711234")
    assert not invalid["can_confirm"]
    assert "controlecijfer" in invalid["blocked_reasons"][0]
    with pytest.raises(ValueError, match="Correctie"):
        confirm(conn, invalid["preview_fingerprint"], "use_other", "8711234")
    assert not conn.writes
    prepared = preview(conn, "use_other", OTHER_GTIN)
    assert prepared["can_confirm"]
    result = confirm(conn, prepared["preview_fingerprint"], "use_other", OTHER_GTIN)
    assert result["gtin"] == OTHER_GTIN
    assert conn.writes == ["retire_exact_central", "replace_manual"]
    assert conn.manual[0]["gtin"] == OTHER_GTIN
    assert conn.manual[0]["global_product_id"] == "new-product"
    assert [e[0] for e in events] == ["materialize", "audit"]


def test_shared_central_link_blocked_for_manual_or_other_choice(context):
    conn, events = context
    conn.links[0]["receipt_text_normalized"] = ""
    for mode, barcode in [("keep_manual", ""), ("use_other", OTHER_GTIN)]:
        checked = preview(conn, mode, barcode)
        assert checked["can_confirm"] is False
        assert any("gedeelde koppeling" in message for message in checked["blocked_reasons"])
        with pytest.raises(ValueError, match="Correctie"):
            confirm(conn, checked["preview_fingerprint"], mode, barcode)
    assert preview(conn, "keep_catalog")["can_confirm"] is True
    assert not conn.writes and not events


def test_preview_fingerprint_detects_stale_manual_or_central_changes(context):
    conn, events = context
    checked = preview(conn)
    conn.manual[0]["updated_at"] = "2026-11-02"
    with pytest.raises(ValueError, match="veranderd"):
        confirm(conn, checked["preview_fingerprint"])
    assert not conn.writes and not events
    conn.manual[0]["updated_at"] = "2026-11-01"
    conn.links[0]["global_product_id"] = "other-product"
    with pytest.raises(ValueError, match="veranderd"):
        confirm(conn, checked["preview_fingerprint"])
    assert not conn.writes and not events


def test_ambiguous_retailer_links_and_absent_actor_fail_closed(context):
    conn, events = context
    conn.links.append({**conn.links[0], "id": "second-id"})
    assert not preview(conn)["can_confirm"]
    with pytest.raises(ValueError, match="bevestiger"):
        confirm(conn, "a" * 64, actor="")
    assert not conn.writes and not events
