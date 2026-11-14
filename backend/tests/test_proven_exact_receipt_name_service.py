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
    assert not candidates
    # The saved barcode itself is blocked, as is the unrelated article that
    # would otherwise inherit the disputed name. Never reduce safety to
    # satisfy the historical one-blocked assertion.
    assert blocked == (2 if extra.get("manual_barcode") else 1)


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



def test_identical_names_different_article_numbers_and_shops_all_match():
    items = [
        row("ah", "HALFVOLLE MELK", "101", "milk", "catalog_linked"),
        row("ah", "HALFVOLLE MELK", "456"),
        row("jumbo", "HALFVOLLE MELK", "789"),
        row("plus", "HALFVOLLE MELK", ""),
        row("lidl", "HALFVOLLE MELK 2 L", "222"),
    ]
    matches, blocked, no_proof = service._candidate_plan(items)
    assert {(m["source_key"][0], m["source_key"][2], m["product_id"])
            for m in matches} == {
                ("ah", "456", "milk"), ("jumbo", "789", "milk"),
                ("plus", "", "milk"),
            }
    assert blocked == 0 and no_proof == 1


def test_hv_melk_confirmed_alias_targets_every_store_and_code(monkeypatch):
    items = [
        row("ah", "Halfvolle melk", "101", "milk", "catalog_linked"),
        row("ah", "HV Melk", "900"),
        row("jumbo", "HV Melk", "987"),
        row("lidl", "HV Melk", ""),
    ]
    aliases = {"hv melk": {"target_name": "halfvolle melk", "product_id": "milk"}}
    matches, blocked, no_proof = service._candidate_plan(items, aliases)
    assert {(m["source_key"][0], m["source_key"][2])
            for m in matches} == {("ah", "900"), ("jumbo", "987"), ("lidl", "")}
    assert all(m["product_id"] == "milk" and
               m["proof_name"] == "halfvolle melk" for m in matches)
    assert blocked == no_proof == 0
    monkeypatch.setattr(service, "load_confirmed_bonnaam_aliases",
                        lambda conn: aliases)
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": items})
    def source_lookup(conn, rid):
        name, code = ("HV Melk", rid.split("-")[-1])
        return {"retailer_code": rid.split(":")[-1].split("-")[0],
                "receipt_text": name,
                "external_article_code": "" if code == "empty" else code}
    monkeypatch.setattr(service, "resolve_external_article_identity", source_lookup)
    stored = []
    monkeypatch.setattr(service, "_persist_exact_name_match",
                        lambda conn, **kw: stored.append(kw) or True)
    result = service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam")
    assert result["linked"] == 3
    assert result["linked_without_article_number"] == 1
    assert {m["source_key"][2] for m in stored} == {"900", "987", ""}


def test_same_name_two_proven_different_code_destinations_stays_blocked():
    items = [
        row("ah", "Melk", "100", "product-a", "catalog_linked"),
        row("ah", "Melk", "200", "product-b", "catalog_linked"),
        row("jumbo", "Melk", "300"),
    ]
    assert service._candidate_plan(items)[0] == []
    assert service._candidate_plan(items)[1] == 1


def test_alias_never_overwrites_conflicting_preconfirmed_source():
    items = [
        row("ah", "HALFVOLLE MELK", "123", "milk", "catalog_linked"),
        row("lidl", "HV Melk", "55", "other", "catalog_linked"),
        row("jumbo", "HV Melk", "77"),
    ]
    aliases = {"hv melk": {"target_name": "halfvolle melk", "product_id": "milk"}}
    assert service._candidate_plan(items, aliases)[0] == []
    assert service._candidate_plan(items, aliases)[1] == 1


def test_alias_confirmation_requires_proven_name_and_blocks_conflicts(monkeypatch):
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": [row("jumbo", "HV Melk")]})
    with pytest.raises(ValueError, match="geen unieke"):
        service.confirm_bonnaam_alias(FakeConn(), alias_name="HV Melk",
                                     target_name="Halfvolle melk", actor_id="frontteam")
    records = [
        row("ah", "Halfvolle melk", "12", "milk", "catalog_linked"),
        row("lidl", "HV Melk", "88", "other", "catalog_linked"),
    ]
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": records})
    monkeypatch.setattr(service, "_ensure_active_product",
                        lambda conn, product_id: True)
    with pytest.raises(ValueError, match="tegenstrijdige"):
        service.confirm_bonnaam_alias(FakeConn(), alias_name="HV Melk",
                                     target_name="Halfvolle melk", actor_id="frontteam")
    records.pop()
    monkeypatch.setattr(service, "load_confirmed_bonnaam_aliases",
                        lambda conn: {"halfvolle melk": {
                            "target_name": "verse melk", "product_id": "milk"}})
    with pytest.raises(ValueError, match="zelf een alias"):
        service.confirm_bonnaam_alias(FakeConn(), alias_name="HV Melk",
                                     target_name="Halfvolle melk", actor_id="frontteam")


def test_unified_bonnamen_matchen_combines_both_authorities(monkeypatch):
    from app.api import catalog_routes as api
    events = []
    monkeypatch.setattr(api, "_require_authorized_bonnaam_actor",
                        lambda: SimpleNamespace(user_id="frontteam"))
    @contextmanager
    def transaction():
        events.append("begin")
        yield FakeConn()
        events.append("commit")
    monkeypatch.setattr(api, "engine", SimpleNamespace(begin=transaction))
    monkeypatch.setattr(api, "automatically_match_curated_receipts",
                        lambda conn, *, actor_id: {
                            "ok": True, "status": "applied", "linked": 2,
                            "synonyms_created": 1, "blocked": 0})
    monkeypatch.setattr(api, "automatically_match_proven_exact_names",
                        lambda conn, *, actor_id: {
                            "ok": True, "linked": 3, "blocked": 1})
    response = api.auto_ed2_bonnamen_matchen()
    assert events == ["begin", "commit"]
    assert response["linked"] == 5
    assert response["linked_from_exact_names"] == 3
    assert response["linked_from_families"] == 2
    assert response["synonyms_created"] == 1
    assert response["blocked"] == 1
    assert response["barcode_written"] is False


def test_unified_alias_routes_deny_nonprivileged_user_before_db(monkeypatch):
    from app.api import catalog_routes as api
    from fastapi import HTTPException
    monkeypatch.setattr(api, "require_platform_permission_from_session",
                        lambda *_: SimpleNamespace(user_id="regular",
                            is_platform_superuser=False, is_frontteam=False))
    class NeverConnect:
        def begin(self):
            pytest.fail("Ordinary user may not start central identity transaction")
    monkeypatch.setattr(api, "engine", NeverConnect())
    with pytest.raises(HTTPException) as error:
        api.auto_ed2_bonnamen_matchen()
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        api.confirm_ed2_bonnaam_synoniem(
            api.Ed2BonnaamAliasConfirmation(alias_name="HV Melk",
                                             target_name="Halfvolle melk"))
    assert error.value.status_code == 403


def test_large_batch_refreshes_full_overview_only_twice(monkeypatch):
    # Regression for the 14-Nov local diagnostic: the old 50-candidate
    # implementation performed 51 full ED2 projections, each 15-17 seconds.
    sources = [row("ah", "Halfvolle melk", "100", "milk", "catalog_linked")]
    sources.extend(
        row("jumbo", "Halfvolle melk", str(number))
        for number in range(50)
    )
    observations = {"full_scans": 0, "confirmed": 0}
    def projected(*, conn):
        observations["full_scans"] += 1
        return {"items": sources}
    monkeypatch.setattr(service, "list_all_external_articles", projected)
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, receipt_id: {
                            "retailer_code": "jumbo", "receipt_text": "Halfvolle melk",
                            "external_article_code": receipt_id.rsplit("-", 1)[-1],
                        })
    def persisted(conn, **kwargs):
        observations["confirmed"] += 1
        return True
    monkeypatch.setattr(service, "_persist_exact_name_match", persisted)
    result = service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam")
    assert result["linked"] == 50
    assert observations["confirmed"] == 50
    assert observations["full_scans"] == 2
    assert result["limit_reached"] is False


def test_changed_proof_across_two_batch_snapshots_blocks_every_write(monkeypatch):
    sources = [row("ah", "Boter", "123", "butter", "catalog_linked"),
               row("jumbo", "Boter", "987")]
    views = [
        sources,
        [row("ah", "Boter", "123", "different", "catalog_linked"),
         row("jumbo", "Boter", "987")],
    ]
    scans = {"count": 0}
    def projected(*, conn):
        scans["count"] += 1
        return {"items": views[min(scans["count"] - 1, 1)]}
    monkeypatch.setattr(service, "list_all_external_articles", projected)
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, item: {
                            "retailer_code": "jumbo", "receipt_text": "Boter",
                            "external_article_code": "987",
                        })
    monkeypatch.setattr(service, "_persist_exact_name_match",
                        lambda *args, **kwargs: pytest.fail("A changed proof must never write"))
    result = service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam")
    assert result["linked"] == 0
    assert result["blocked"] >= 1
    assert scans["count"] == 2
