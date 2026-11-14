"""Universal exact-name receipt matching: proven coded sources, never name guesses."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services import proven_exact_receipt_name_service as service


@pytest.fixture(autouse=True)
def default_no_confirmed_aliases(monkeypatch):
    monkeypatch.setattr(service, 'load_confirmed_bonnaam_aliases', lambda conn: {})


def row(shop, name, code="", product="", status="not_identified", **extras):
    return {
        "id": f"receipt-table-line:{shop}-{name}-{code or 'empty'}",
        "retailer_code": shop, "receipt_line_text": name,
        "receipt_article_number": code, "identity_status": status,
        "identity_catalog_product_id": product, "catalog_product_id": "",
        **extras,
    }


def test_all_product_categories_and_retailers_reuse_exact_coded_proof_only():
    items = [
        row("ah", "HALFVOLLE MELK", "101", "milk", "catalog_linked"),
        row("jumbo", "HALFVOLLE MELK"),
        row("plus", "Halfvolle-Melk"),
        row("lidl", "Heel volkoren brood", "02", "bread", "catalog_linked"),
        row("aldi", "Heel volkoren brood"),
        row("ah", "volle melk"),  # similar, not identical
        row("jumbo", "HALFVOLLE MELK 1 L"),  # different package
        row("lidl", "Courgette geel", "0082293", "yellow", "catalog_linked"),
        row("picnic", "Courgette geel"),
    ]
    candidates, blocked, missing = service._candidate_plan(items)
    assert {(item["source_key"][0], item["product_id"]) for item in candidates} == {
        ("jumbo", "milk"), ("plus", "milk"), ("aldi", "bread"), ("picnic", "yellow")}
    assert all(item["source_key"][2] == "" for item in candidates)
    assert blocked == 0 and missing == 2


def test_two_proven_destinations_for_identical_name_block_every_candidate():
    rows = [row("ah", "BROOD", "12", "a", "catalog_linked"),
            row("lidl", "BROOD", "99", "b", "catalog_linked"),
            row("jumbo", "BROOD")]
    candidates, blocked, unproven = service._candidate_plan(rows)
    assert candidates == [] and blocked == 1 and unproven == 0


@pytest.mark.parametrize("status,extra", [
    ("review", {}),
    ("saved_only", {}),
    ("not_identified", {"manual_barcode": "8712345678906"}),
])
def test_disputed_source_prevents_automatic_name_inheritance(status, extra):
    rows = [row("ah", "Melk", "123", "milk", "catalog_linked"),
            row("lidl", "Melk", "456", status=status, **extra),
            row("jumbo", "Melk")]
    candidates, blocked, _ = service._candidate_plan(rows)
    assert not candidates and blocked == 1


def test_conflicting_catalog_proof_cannot_be_used_as_source():
    rows = [row("ah", "Tomaten", "111", "p1", "catalog_linked",
                catalog_product_id="p2"),
            row("jumbo", "Tomaten")]
    assert service._candidate_plan(rows)[0] == []


def test_code_free_only_can_never_prove_another_code_free_source():
    rows = [row("ah", "Melk", "", "milk", "catalog_linked"),
            row("jumbo", "Melk")]
    assert service._candidate_plan(rows)[0] == []


def test_unrelated_products_and_removed_identity_are_not_guessed():
    rows = [row("lidl", "Courgettesoep", "42", "soup", "catalog_linked"),
            row("ah", "Courgette"), row("lidl", "Olvarit Courgette")]
    assert service._candidate_plan(rows)[0] == []


class FakeConn:
    dialect = SimpleNamespace(name="postgresql")
    def __init__(self):
        self.commands = []
    def execute(self, stmt, params=None):
        self.commands.append((str(stmt), params or {}))
        return SimpleNamespace()
    @contextmanager
    def begin_nested(self):
        yield self


def test_batch_authorized_action_applies_only_safe_rows_and_is_idempotent(monkeypatch):
    items = [row("ah", "HALFVOLLE MELK", "101", "milk", "catalog_linked"),
             row("jumbo", "HALFVOLLE MELK")]
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": items})
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, rid: {"retailer_code": "jumbo",
                                          "receipt_text": "HALFVOLLE MELK",
                                          "external_article_code": ""})
    applied = []
    monkeypatch.setattr(service, "_persist_exact_name_match",
                        lambda conn, **kw: applied.append(kw) or True)
    result = service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam-1")
    assert result["linked"] == 1
    assert result["synonyms_created"] == 0
    assert result["barcode_written"] is False
    assert applied[0]["product_id"] == "milk"
    assert applied[0]["source_key"] == ("jumbo", "halfvolle melk", "")
    assert applied[0]["witness"]["receipt_article_number"] == "101"
    # Once projected as catalog-linked, repeating the batch must not write.
    items[-1]["identity_status"] = "catalog_linked"
    assert service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam-1")["linked"] == 0
    assert len(applied) == 1


def test_changed_source_or_changed_proof_never_writes(monkeypatch):
    initial = [row("ah", "Boter", "123", "butter", "catalog_linked"),
               row("jumbo", "Boter")]
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": initial})
    monkeypatch.setattr(service, "_persist_exact_name_match",
                        lambda *args, **kwargs: pytest.fail("Never persist stale evidence"))
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, rid: {"retailer_code": "jumbo",
                                          "receipt_text": "Boter Extra",
                                          "external_article_code": ""})
    assert service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="admin")["linked"] == 0

    hits = {"calls": 0}
    def source_rows(*, conn):
        hits["calls"] += 1
        return {"items": initial if hits["calls"] == 1 else initial[:1]}
    monkeypatch.setattr(service, "list_all_external_articles", source_rows)
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, rid: {"retailer_code": "jumbo",
                                          "receipt_text": "Boter",
                                          "external_article_code": ""})
    assert service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="admin")["linked"] == 0


def test_batch_rejects_wrong_database_and_missing_actor():
    with pytest.raises(ValueError, match="PostgreSQL"):
        service.automatically_match_proven_exact_names(
            SimpleNamespace(dialect=SimpleNamespace(name="sqlite")), actor_id="admin")
    with pytest.raises(ValueError, match="geautoriseerde"):
        service.automatically_match_proven_exact_names(FakeConn(), actor_id="")


def test_authorization_denies_ordinary_users_before_database_transaction(monkeypatch):
    from app.api import catalog_routes
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda *_: SimpleNamespace(user_id="ordinary",
                            is_platform_superuser=False, is_frontteam=False))
    class NoTransaction:
        def begin(self):
            pytest.fail("An ordinary user may not begin a transaction")
    monkeypatch.setattr(catalog_routes, "engine", NoTransaction())
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        catalog_routes.auto_ed2_proven_exact_names()
    assert exc.value.status_code == 403


def test_frontteam_can_run_one_authorized_transaction(monkeypatch):
    from app.api import catalog_routes
    events = []
    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session",
                        lambda *_: SimpleNamespace(user_id="frontteam",
                            is_platform_superuser=False, is_frontteam=True))
    @contextmanager
    def begin():
        events.append("begin")
        yield FakeConn()
        events.append("commit")
    monkeypatch.setattr(catalog_routes, "engine", SimpleNamespace(begin=begin))
    monkeypatch.setattr(catalog_routes, "automatically_match_proven_exact_names",
                        lambda conn, *, actor_id: {"ok": True, "actor": actor_id})
    assert catalog_routes.auto_ed2_proven_exact_names()["actor"] == "frontteam"
    assert events == ["begin", "commit"]
