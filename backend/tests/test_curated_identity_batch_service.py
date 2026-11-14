"""Curated ED2 batch: read-only proposals, evidence guards, no invented barcodes."""
from types import SimpleNamespace

import pytest

from app.services import curated_identity_batch_service as batch


ROOT = {"id": "ah-courgette", "name": "AH Courgette", "variant": "",
        "primary_gtin": "8722800072026", "article_codes": ["ah:21003"]}
SOURCES = [
    {"id": "receipt-table-line:ah-linked", "receipt_line_text": "COURGETTE",
     "retailer_code": "ah", "receipt_article_number": "21003",
     "identity_status": "catalog_linked", "article_code": "8722800072026",
     "manual_barcode": ""},
    {"id": "receipt-table-line:ah", "receipt_line_text": "COURGETTE",
     "retailer_code": "ah", "receipt_article_number": "",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:jumbo", "receipt_line_text": "COURGETTE",
     "retailer_code": "jumbo", "receipt_article_number": "",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:lidl", "receipt_line_text": "Courgette groen",
     "retailer_code": "lidl", "receipt_article_number": "0082346",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:lidl2", "receipt_line_text": "Courgette groen",
     "retailer_code": "lidl", "receipt_article_number": "",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:yellow", "receipt_line_text": "Courgette geel",
     "retailer_code": "lidl", "receipt_article_number": "0082293",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:bio", "receipt_line_text": "Courgette Bio",
     "retailer_code": "lidl", "receipt_article_number": "0084544",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:baby", "receipt_line_text": "Olvarit Courgette",
     "retailer_code": "ah", "receipt_article_number": "",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
    {"id": "receipt-table-line:frozen", "receipt_line_text": "Diepvries courgette",
     "retailer_code": "ah", "receipt_article_number": "",
     "identity_status": "not_identified", "article_code": "", "manual_barcode": ""},
]


def _setup(monkeypatch, blocked=None):
    monkeypatch.setattr(batch, "load_products", lambda conn: [ROOT])
    monkeypatch.setattr(batch, "list_all_external_articles",
                        lambda *, conn: {"items": SOURCES})
    blocked = set(blocked or ())
    def guard(conn, source):
        if source.get("external_article_code") in blocked:
            raise ValueError("Een bestaande barcodeclaim blokkeert dit artikel.")
    monkeypatch.setattr(batch, "_guard_preexisting_claims", guard)


def test_po_seven_courgettes_preview_six_safe_proposals(monkeypatch):
    _setup(monkeypatch)
    conn = SimpleNamespace()
    options = batch.matching_batch_preview(conn)
    assert [r["product_id"] for r in options["targets"]] == [ROOT["id"]]
    assert options["items"] == []
    plan = batch.matching_batch_preview(conn, target_product_id=ROOT["id"])
    assert len(plan["items"]) == 6
    assert len(plan["blocked"]) == 0
    assert sorted(row["mode"] for row in plan["items"]) == [
        "same_product", "same_product", "same_product", "same_product",
        "synonym_variant", "synonym_variant",
    ]
    assert len(plan["fingerprint"]) == 64
    assert all(row["receipt_item_id"] not in {"receipt-table-line:baby",
               "receipt-table-line:frozen", "receipt-table-line:ah-linked"}
               for row in plan["items"])


def test_preexisting_claim_blocks_specific_article_not_other_candidates(monkeypatch):
    _setup(monkeypatch, blocked={"0082346"})
    plan = batch.matching_batch_preview(SimpleNamespace(),
                                        target_product_id=ROOT["id"])
    assert len(plan["items"]) == 5
    assert len(plan["blocked"]) == 1
    assert plan["blocked"][0]["receipt_article_number"] == "0082346"


def test_no_name_only_batch_can_invent_root_or_barcode(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError, match="bewezen"):
        batch.matching_batch_preview(SimpleNamespace(), target_product_id="fictitious")
    monkeypatch.setattr(batch, "load_products",
                        lambda conn: [{**ROOT, "primary_gtin": "", "article_codes": []}])
    assert batch.matching_batch_preview(SimpleNamespace())["targets"] == []


def test_confirm_requires_postgresql_and_review_fingerprint(monkeypatch):
    _setup(monkeypatch)
    with pytest.raises(ValueError, match="PostgreSQL"):
        batch.confirm_matching_batch(SimpleNamespace(dialect=SimpleNamespace(name="sqlite")),
            target_product_id=ROOT["id"], receipt_item_ids=["receipt-table-line:lidl"],
            expected_fingerprint="0" * 64, actor_id="superuser")
    with pytest.raises(ValueError, match="voorbeeldlijst"):
        batch.confirm_matching_batch(SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
            target_product_id=ROOT["id"], receipt_item_ids=["receipt-table-line:lidl"],
            expected_fingerprint="0" * 64, actor_id="superuser")


def test_atomic_confirm_rechecks_exact_sources_and_never_writes_gtins(monkeypatch):
    _setup(monkeypatch)
    conn = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    plan = batch.matching_batch_preview(conn, target_product_id=ROOT["id"])
    selected = ["receipt-table-line:lidl", "receipt-table-line:yellow"]
    sources = {row["id"]: row for row in SOURCES}
    monkeypatch.setattr(batch, "resolve_external_article_identity", lambda conn, rid: {
        "retailer_code": sources[rid]["retailer_code"],
        "receipt_text": sources[rid]["receipt_line_text"],
        "external_article_code": sources[rid]["receipt_article_number"],
    })
    calls = []
    def confirmed(conn, **kwargs):
        calls.append(kwargs)
        return {"synonym_created": kwargs["match_mode"] == "synonym_variant",
                "barcode_written": False}
    monkeypatch.setattr(batch, "confirm_courgette_receipt", confirmed)
    result = batch.confirm_matching_batch(
        conn, target_product_id=ROOT["id"], receipt_item_ids=selected,
        expected_fingerprint=plan["fingerprint"], actor_id="superuser",
    )
    assert result == {"ok": True, "linked": 2, "synonyms_created": 1,
                      "barcode_written": False, "receipt_changes": 0,
                      "household_changes": 0, "stock_changes": 0}
    assert [item["receipt_item_id"] for item in calls] == selected
    assert [item["match_mode"] for item in calls] == ["same_product", "synonym_variant"]


def test_partial_or_duplicate_or_outdated_selection_is_rejected(monkeypatch):
    _setup(monkeypatch)
    conn = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    plan = batch.matching_batch_preview(conn, target_product_id=ROOT["id"])
    for ids in ([], ["receipt-table-line:ah"] * 2, ["receipt-table-line:baby"]):
        with pytest.raises(ValueError):
            batch.confirm_matching_batch(conn, target_product_id=ROOT["id"],
                receipt_item_ids=ids, expected_fingerprint=plan["fingerprint"],
                actor_id="superuser")



def test_unauthorized_batch_cannot_open_mutating_transaction(monkeypatch):
    from fastapi import HTTPException
    from app.api import catalog_routes

    monkeypatch.setattr(catalog_routes,
        "require_platform_permission_from_session",
        lambda permission: SimpleNamespace(user_id="ordinary",
            is_platform_superuser=False, is_frontteam=False))

    class Engine:
        def begin(self):
            raise AssertionError("Authorization must be checked before opening a transaction")

    monkeypatch.setattr(catalog_routes, "engine", Engine())
    request = catalog_routes.Ed2CuratedMatchingBatchConfirmation(
        target_product_id=ROOT["id"],
        receipt_item_ids=["receipt-table-line:lidl"],
        fingerprint="e" * 64,
    )
    with pytest.raises(HTTPException) as err:
        catalog_routes.confirm_ed2_curated_matching_batch(request)
    assert err.value.status_code == 403


def test_superuser_batch_verifies_fingerprint_inside_transaction(monkeypatch):
    from contextlib import contextmanager
    from fastapi import HTTPException
    from app.api import catalog_routes

    monkeypatch.setattr(catalog_routes,
        "require_platform_permission_from_session",
        lambda permission: SimpleNamespace(user_id="authorized",
            is_platform_superuser=True,
            is_frontteam=False))
    events = []
    @contextmanager
    def begin():
        events.append("begin")
        try:
            yield SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")

    monkeypatch.setattr(catalog_routes, "engine", SimpleNamespace(begin=begin))
    def deliberate_stale(*_args, **_kwargs):
        raise ValueError("De voorbeeldlijst is gewijzigd.")

    monkeypatch.setattr(catalog_routes, "confirm_matching_batch", deliberate_stale)
    request = catalog_routes.Ed2CuratedMatchingBatchConfirmation(
        target_product_id=ROOT["id"],
        receipt_item_ids=["receipt-table-line:lidl"],
        fingerprint="e" * 64,
    )
    with pytest.raises(HTTPException) as err:
        catalog_routes.confirm_ed2_curated_matching_batch(request)
    assert err.value.status_code == 409
    assert events == ["begin", "rollback"]


def test_frontteam_batch_confirmation_denied_before_transaction(monkeypatch):
    from fastapi import HTTPException
    from app.api import catalog_routes
    monkeypatch.setattr(
        catalog_routes, "require_platform_permission_from_session",
        lambda *_: SimpleNamespace(user_id="frontteam",
                                   is_platform_superuser=False, is_frontteam=True))
    class NoTransaction:
        def begin(self):
            pytest.fail("Frontteam may not confirm a central match")
    monkeypatch.setattr(catalog_routes, "engine", NoTransaction())
    payload = catalog_routes.Ed2CuratedMatchingBatchConfirmation(
        target_product_id=ROOT["id"],
        receipt_item_ids=["receipt-table-line:lidl"],
        fingerprint="e" * 64,
    )
    with pytest.raises(HTTPException) as error:
        catalog_routes.confirm_ed2_curated_matching_batch(payload)
    assert error.value.status_code == 403


def test_public_batch_preview_is_read_only_and_authorized(monkeypatch):
    from contextlib import contextmanager
    from app.api import catalog_routes
    calls = []
    def permission(code):
        calls.append(code)
        return SimpleNamespace(user_id="superuser", is_platform_superuser=True,
                               is_frontteam=False)
    monkeypatch.setattr(catalog_routes,
        "require_platform_permission_from_session", permission)
    @contextmanager
    def connect():
        calls.append("open_read_only")
        yield SimpleNamespace()
        calls.append("close_read_only")
    monkeypatch.setattr(catalog_routes, "engine",
                        SimpleNamespace(connect=connect))
    monkeypatch.setattr(catalog_routes, "matching_batch_preview",
                        lambda conn, **kwargs: {"items": [], "targets": []})
    output = catalog_routes.preview_ed2_curated_matching_batch()
    assert output["items"] == []
    assert calls == ["platform.external_products.link_existing",
                     "open_read_only", "close_read_only"]


def test_frontteam_preview_denied_before_database_read(monkeypatch):
    from fastapi import HTTPException
    from app.api import catalog_routes
    monkeypatch.setattr(
        catalog_routes, "require_platform_permission_from_session",
        lambda *_: SimpleNamespace(user_id="frontteam",
                                   is_platform_superuser=False, is_frontteam=True))
    class NoConnection:
        def connect(self):
            pytest.fail("Frontteam may not open Superuser matching preview")
    monkeypatch.setattr(catalog_routes, "engine", NoConnection())
    with pytest.raises(HTTPException) as error:
        catalog_routes.preview_ed2_curated_matching_batch()
    assert error.value.status_code == 403
