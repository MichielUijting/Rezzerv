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
