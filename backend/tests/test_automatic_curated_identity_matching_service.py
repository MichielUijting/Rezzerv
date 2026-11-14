"""Automated curated matching: zero-click strong matches; doubtful cases stay."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import automatic_curated_identity_matching_service as auto


class _Connection:
    dialect = SimpleNamespace(name="postgresql")

    @contextmanager
    def begin_nested(self):
        yield self


def _plan(*, targets=None, items=None, blocked=None):
    return {
        "targets": [{"product_id": "proven-ah"}] if targets is None else targets,
        "items": items or [], "blocked": blocked or [],
    }


def _row(number, mode="same_product"):
    return {
        "receipt_item_id": "receipt-" + (number or "unknown"),
        "source_key": ["lidl", "courgette geel" if mode == "synonym_variant" else "courgette groen", number],
        "receipt_article_number": number,
        "mode": mode, "target_fingerprint": "a" * 64,
    }


def test_auto_matches_only_independent_retailer_codes_and_never_barcodes(monkeypatch):
    rows = [_row("001"), _row("002", "synonym_variant"), _row("")]
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda conn, target_product_id=None: _plan(items=rows))
    monkeypatch.setattr(auto, "resolve_external_article_identity",
                        lambda conn, item_id: {
                            "retailer_code": "lidl",
                            "receipt_text": "courgette geel" if item_id == "receipt-002" else "courgette groen",
                            "external_article_code": item_id.split("-")[-1] if item_id != "receipt-unknown" else "",
                        })
    calls = []
    def confirm(conn, **kwargs):
        calls.append(kwargs)
        return {"synonym_created": kwargs["match_mode"] == "synonym_variant",
                "barcode_written": False}
    monkeypatch.setattr(auto, "confirm_courgette_receipt", confirm)
    monkeypatch.setattr(auto, "list_all_external_articles",
                        lambda *, conn: {"items": []})
    monkeypatch.setattr(auto, "load_products", lambda conn: [])
    result = auto.automatically_match_curated_receipts(_Connection(), actor_id="frontteam-1")
    assert result["linked"] == 2
    assert result["synonyms_created"] == 1
    assert result["unprocessed"] == 1
    assert result["requires_review"] is True
    assert result["barcode_written"] is False
    assert all(call["automatic"] is True and call["actor_id"] == "frontteam-1"
               for call in calls)
    assert len(calls) == 2


def test_ambiguous_catalog_anchor_is_never_automatically_selected(monkeypatch):
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(targets=[
                            {"product_id": "ah"}, {"product_id": "other"},
                        ]))
    result = auto.automatically_match_curated_receipts(_Connection(), actor_id="superuser")
    assert result["linked"] == 0
    assert result["status"] == "anchor_review_required"
    assert result["requires_review"] is True


def test_one_conflict_keeps_other_safe_rows_without_partial_conflicted_write(monkeypatch):
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(items=[_row("001"), _row("002")],
                                                         blocked=[{"reason": "another code"}]))
    monkeypatch.setattr(auto, "resolve_external_article_identity",
                        lambda conn, item_id: {
                            "retailer_code": "lidl", "receipt_text": "courgette groen",
                            "external_article_code": item_id.split("-")[-1],
                        })
    def confirm(conn, **kwargs):
        if kwargs["source"]["external_article_code"] == "001":
            raise ValueError("conflict")
        return {"synonym_created": False}
    monkeypatch.setattr(auto, "confirm_courgette_receipt", confirm)
    output = auto.automatically_match_curated_receipts(_Connection(), actor_id="superuser")
    assert output["linked"] == 1
    assert output["blocked"] == 2
    assert output["requires_review"] is True


def test_post_refuses_nonprivileged_users_before_transaction(monkeypatch):
    from fastapi import HTTPException
    from app.api import catalog_routes
    monkeypatch.setattr(
        catalog_routes, "require_platform_permission_from_session",
        lambda *_: SimpleNamespace(user_id="ordinary",
                                  is_platform_superuser=False, is_frontteam=False),
    )
    class NoTransaction:
        def begin(self):
            raise AssertionError("Unauthorized callers must never open a write transaction")
    monkeypatch.setattr(catalog_routes, "engine", NoTransaction())
    with pytest.raises(HTTPException) as error:
        catalog_routes.auto_ed2_curated_matching_batch()
    assert error.value.status_code == 403


def test_post_authorizes_frontteam_and_uses_transaction(monkeypatch):
    from app.api import catalog_routes
    events = []
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda *_: SimpleNamespace(
                            user_id="frontteam-1", is_platform_superuser=False,
                            is_frontteam=True))
    @contextmanager
    def begin():
        events.append("begin")
        yield _Connection()
        events.append("commit")
    monkeypatch.setattr(catalog_routes, "engine", SimpleNamespace(begin=begin))
    monkeypatch.setattr(catalog_routes, "automatically_match_curated_receipts",
                        lambda conn, *, actor_id: {"ok": True, "actor": actor_id})
    assert catalog_routes.auto_ed2_curated_matching_batch()["actor"] == "frontteam-1"
    assert events == ["begin", "commit"]


# New PO rule: a code-free EXACT receipt name may reuse a unique already
# confirmed code-bearing receipt identity. Never assume a merely similar name
# or create a GTIN, duplicate product, or fresh synonym relation.
def _catalog_product(pid="proven-ah", name="AH Courgette"):
    return {"id": pid, "name": name, "variant": "",
            "primary_gtin": "8722800072026" if pid == "proven-ah" else "",
            "article_codes": ["ah:21003"]}


def _proven_receipt(shop, name, code, pid="proven-ah", status="catalog_linked"):
    return {"id": "confirmed-" + shop + "-" + code,
            "retailer_code": shop, "receipt_line_text": name,
            "receipt_article_number": code, "identity_status": status,
            "identity_catalog_product_id": pid,
            "catalog_product_id": ""}


def _code_free(shop, name):
    from app.services.external_article_product_link_service import (
        normalize_external_link_receipt_text,
    )
    return {
        "receipt_item_id": shop + ":no-code",
        "source_key": [shop, normalize_external_link_receipt_text(name), ""],
        "receipt_article_number": "", "mode": "same_product",
        "target_fingerprint": "a" * 64,
    }


def test_exact_code_free_receipt_names_reuse_confirmed_product_across_shops(monkeypatch):
    proven = [
        _proven_receipt("ah", "COURGETTE", "21003"),
        _proven_receipt("lidl", "Courgette groen", "0082346"),
    ]
    rows = [_code_free("ah", "COURGETTE"),
            _code_free("jumbo", "COURGETTE"),
            _code_free("lidl", "Courgette groen")]
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(items=rows))
    monkeypatch.setattr(auto, "load_products", lambda conn: [_catalog_product()])
    monkeypatch.setattr(auto, "list_all_external_articles",
                        lambda *, conn: {"items": proven})
    monkeypatch.setattr(auto, "resolve_external_article_identity",
                        lambda conn, rid: {
                            "retailer_code": rid.split(":")[0],
                            "receipt_text": "Courgette groen" if rid.startswith("lidl") else "COURGETTE",
                            "external_article_code": "",
                        })
    confirmed = []
    def write(conn, **kwargs):
        confirmed.append(kwargs)
        return {"already_confirmed": False, "synonym_created": False, "barcode_written": False}
    monkeypatch.setattr(auto, "confirm_courgette_receipt", write)
    summary = auto.automatically_match_curated_receipts(_Connection(), actor_id="frontteam")
    assert summary["linked"] == 3
    assert summary["linked_without_article_number"] == 3
    assert summary["unprocessed"] == 0
    assert summary["synonyms_created"] == 0
    assert summary["barcode_written"] is False
    assert len(confirmed) == 3
    assert all(call["target_product_id"] == "proven-ah" and
               call["match_mode"] == "same_product" and
               call["automatic"] is True and
               call["source"]["external_article_code"] == ""
               for call in confirmed)


def test_exact_name_ambiguity_and_unverified_sources_never_mutate(monkeypatch):
    proofs = [
        _proven_receipt("ah", "COURGETTE", "21003"),
        _proven_receipt("jumbo", "COURGETTE", "17001", "another-product"),
    ]
    monkeypatch.setattr(auto, "load_products",
                        lambda conn: [_catalog_product(), _catalog_product("another-product")])
    monkeypatch.setattr(auto, "list_all_external_articles",
                        lambda *, conn: {"items": proofs})
    assert "courgette" not in auto._independently_proven_exact_names(_Connection())
    proofs[1]["identity_status"] = "review"
    assert "courgette" not in auto._independently_proven_exact_names(_Connection())
    proofs[1]["identity_status"] = "not_identified"
    assert auto._independently_proven_exact_names(_Connection())["courgette"]["id"] == "proven-ah"
    proofs[0]["receipt_article_number"] = ""
    assert "courgette" not in auto._independently_proven_exact_names(_Connection())


def test_code_free_near_match_does_not_inherit_other_label(monkeypatch):
    rows = [_code_free("lidl", "Courgette groen")]
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(items=rows))
    monkeypatch.setattr(auto, "load_products", lambda conn: [_catalog_product()])
    monkeypatch.setattr(auto, "list_all_external_articles",
                        lambda *, conn: {"items": [_proven_receipt("ah", "COURGETTE", "21003")]})
    monkeypatch.setattr(auto, "confirm_courgette_receipt",
                        lambda *a, **kw: pytest.fail("No name-only near-match may write"))
    result = auto.automatically_match_curated_receipts(_Connection(), actor_id="frontteam")
    assert result["linked"] == 0
    assert result["unprocessed"] == 1
    assert result["requires_review"] is True


def test_code_free_proof_is_rechecked_in_transaction(monkeypatch):
    rows = [_code_free("ah", "COURGETTE")]
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(items=rows))
    monkeypatch.setattr(auto, "load_products", lambda conn: [_catalog_product()])
    seq = {"calls": 0}
    def proof_lookup(*, conn):
        seq["calls"] += 1
        return {"items": [_proven_receipt("ah", "COURGETTE", "21003")]
                if seq["calls"] == 1 else []}
    monkeypatch.setattr(auto, "list_all_external_articles", proof_lookup)
    monkeypatch.setattr(auto, "resolve_external_article_identity",
                        lambda conn, rid: {
                            "retailer_code": "ah", "receipt_text": "COURGETTE",
                            "external_article_code": "",
                        })
    monkeypatch.setattr(auto, "confirm_courgette_receipt",
                        lambda *a, **kw: pytest.fail("Stale proof must never write"))
    result = auto.automatically_match_curated_receipts(_Connection(), actor_id="frontteam")
    assert result["linked"] == 0
    assert result["blocked"] == 1
    assert result["unprocessed"] == 1
    assert seq["calls"] >= 2


def test_code_free_variant_uses_proven_existing_variant_not_duplicate_product(monkeypatch):
    products = [_catalog_product(), _catalog_product("yellow-product", "Courgette geel")]
    row = _code_free("lidl", "Courgette geel")
    row["mode"] = "synonym_variant"  # Preview against ordinary root
    monkeypatch.setattr(auto, "matching_batch_preview",
                        lambda *args, **kwargs: _plan(items=[row]))
    monkeypatch.setattr(auto, "load_products", lambda conn: products)
    monkeypatch.setattr(auto, "list_all_external_articles",
                        lambda *, conn: {"items": [_proven_receipt("lidl", "Courgette geel",
                                                                  "0082293", "yellow-product")]})
    monkeypatch.setattr(auto, "resolve_external_article_identity",
                        lambda conn, rid: {
                            "retailer_code": "lidl", "receipt_text": "Courgette geel",
                            "external_article_code": "",
                        })
    calls = []
    monkeypatch.setattr(auto, "confirm_courgette_receipt",
                        lambda conn, **kwargs: calls.append(kwargs) or {"synonym_created": False})
    output = auto.automatically_match_curated_receipts(_Connection(), actor_id="frontteam")
    assert output["linked_without_article_number"] == 1
    assert output["synonyms_created"] == 0
    assert calls[0]["target_product_id"] == "yellow-product"
    assert calls[0]["match_mode"] == "same_product"
