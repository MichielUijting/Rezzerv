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



def test_lidl_aardappel_zoet_confirmed_gtin_without_shop_number_proves_0080755():
    """PO reproduction: the code-free linked GTIN is independent product proof."""
    items = [
        row("lidl", "Aardappel zoet", "", "sweet-potato",
            "catalog_linked", article_code="4056489846932"),
        row("lidl", "Aardappel zoet", "0080755"),
    ]
    matches, blocked, no_proof = service._candidate_plan(items)
    assert len(matches) == 1
    assert matches[0]["source_key"] == ("lidl", "aardappel zoet", "0080755")
    assert matches[0]["product_id"] == "sweet-potato"
    assert matches[0]["witness"]["receipt_article_number"] == ""
    assert matches[0]["witness"]["confirmed_barcode"] == "4056489846932"
    assert blocked == no_proof == 0


def test_confirmed_codefree_barcode_can_prove_same_name_at_other_stores():
    items = [
        row("lidl", "Aardappel zoet", "", "sweet-potato",
            "catalog_linked", article_code="4056489846932"),
        row("ah", "Aardappel zoet", "9911"),
        row("jumbo", "Aardappel zoet", ""),
        row("lidl", "Aardappel zoet", "0080755"),
    ]
    matches, blocked, no_proof = service._candidate_plan(items)
    assert {(m["source_key"][0], m["source_key"][2], m["product_id"])
            for m in matches} == {
        ("ah", "9911", "sweet-potato"),
        ("jumbo", "", "sweet-potato"),
        ("lidl", "0080755", "sweet-potato"),
    }
    assert blocked == no_proof == 0


def test_saved_only_barcode_or_unverified_gtin_is_not_an_independent_witness():
    pending = row("lidl", "Aardappel zoet", "0080755")
    merely_saved = row("lidl", "Aardappel zoet", "",
                       status="saved_only", manual_barcode="4056489846932")
    candidates, blocked, _ = service._candidate_plan([merely_saved, pending])
    assert candidates == [] and blocked == 1

    for extras in (
        {"article_code": "4056489846932", "barcode_free_catalog_link": True},
        {"article_code": "1234567890123"},  # wrong GTIN check digit
        {},
    ):
        linked = row("lidl", "Aardappel zoet", "", "sweet-potato",
                     "catalog_linked", **extras)
        matches, _, missing = service._candidate_plan([linked, pending])
        assert matches == [] and missing == 1


def test_confirmed_manual_barcode_without_shop_number_is_valid_proof():
    items = [
        row("lidl", "Aardappel zoet", "", "sweet-potato",
            "catalog_linked", manual_barcode="4056489846932"),
        row("lidl", "Aardappel zoet", "0080755"),
    ]
    matches, blocked, _ = service._candidate_plan(items)
    assert len(matches) == 1 and blocked == 0
    assert matches[0]["witness"]["confirmed_barcode"] == "4056489846932"


def test_conflicting_catalog_or_barcode_claim_still_blocks_aardappel_zoet():
    items = [
        row("lidl", "Aardappel zoet", "", "sweet-potato",
            "catalog_linked", article_code="4056489846932"),
        row("ah", "Aardappel zoet", "22", "other", "catalog_linked"),
        row("lidl", "Aardappel zoet", "0080755"),
    ]
    matches, blocked, _ = service._candidate_plan(items)
    assert matches == [] and blocked == 1

    items.pop(1)
    items[0]["manual_barcode"] = "8712345678906"
    matches, blocked, _ = service._candidate_plan(items)
    assert matches == [] and blocked == 1


def test_confirmed_gtin_anchor_is_used_in_real_batch_flow(monkeypatch):
    items = [
        row("lidl", "Aardappel zoet", "", "sweet-potato",
            "catalog_linked", article_code="4056489846932"),
        row("lidl", "Aardappel zoet", "0080755"),
    ]
    monkeypatch.setattr(service, "list_all_external_articles",
                        lambda *, conn: {"items": items})
    monkeypatch.setattr(service, "resolve_external_article_identity",
                        lambda conn, receipt_id: {
                            "retailer_code": "lidl",
                            "receipt_text": "Aardappel zoet",
                            "external_article_code": "0080755",
                        })
    stored = []
    monkeypatch.setattr(service, "_persist_exact_name_match",
                        lambda conn, **kwargs: stored.append(kwargs) or True)
    response = service.automatically_match_proven_exact_names(
        FakeConn(), actor_id="frontteam")
    assert response["linked"] == 1
    assert response["linked_without_article_number"] == 0
    assert response["barcode_written"] is False
    assert response["synonyms_created"] == 0
    assert stored[0]["source_key"] == ("lidl", "aardappel zoet", "0080755")
    assert stored[0]["product_id"] == "sweet-potato"
    assert stored[0]["witness"]["confirmed_barcode"] == "4056489846932"


def test_bonnaam_alias_can_use_catalog_linked_barcode_only_anchor():
    items = [
        row("lidl", "Halfvolle melk", "", "milk",
            "catalog_linked", article_code="8712345678906"),
        row("jumbo", "HV Melk", "0077"),
    ]
    aliases = {"hv melk": {"target_name": "halfvolle melk", "product_id": "milk"}}
    matches, blocked, missing = service._candidate_plan(items, aliases)
    assert len(matches) == 1
    assert matches[0]["product_id"] == "milk"
    assert matches[0]["witness"]["confirmed_barcode"] == "8712345678906"
    assert blocked == missing == 0



def test_store_prefix_and_suffix_removed_only_during_comparison():
    assert service._matching_name("ah", "AH ELSTAR") == "elstar"
    assert service._matching_name("jumbo", "ELSTAR JUMBO") == "elstar"
    assert service._matching_name("albert-heijn", "Albert Heijn Elstar") == "elstar"
    assert service._matching_name("ah", "ELSTAR AH") == "elstar"
    assert service._matching_name("lidl", "Lidl Avocado") == "avocado"
    assert service._matching_name("aldi", "Basilicum Aldi") == "basilicum"
    assert service._matching_name("ah", "AH") == "ah"
    # Another store's name might be a real label/brand on this receipt.
    assert service._matching_name("lidl", "AH Elstar") == "ah elstar"
    # Do not strip arbitrary interior tokens or meaningful descriptive words.
    assert service._matching_name("ah", "ELSTAR AH EXTRA") == "elstar ah extra"
    assert service._matching_name("ah", "AH KIPFILET GEMARINEERD") == "kipfilet gemarineerd"


def test_ah_elstar_matches_jumbo_elstar_without_rewriting_receipt_identity():
    items = [
        row("ah", "AH ELSTAR", "706911", "elstar", "catalog_linked",
            article_code="8718906836846"),
        row("jumbo", "ELSTAR JUMBO", "2345"),
        row("lidl", "Elstar", "00731"),
        row("lidl", "Elstar rood", "0123"),
    ]
    matches, blocked, missing = service._candidate_plan(items)
    assert [(m["source_key"], m["product_id"], m["proof_name"])
            for m in matches] == [
        (("jumbo", "elstar jumbo", "2345"), "elstar", "elstar"),
        (("lidl", "elstar", "00731"), "elstar", "elstar"),
    ]
    assert blocked == 0 and missing == 1
    assert all(m["witness"]["retailer"] == "ah" for m in matches)


def test_ah_avocado_proof_matches_lidl_avocado_without_shop_number_guessing():
    items = [
        row("ah", "AH AVOCADO", "597702", "avocado", "catalog_linked",
            article_code="8710400417330"),
        row("ah", "AVOCADO", "571118", "avocado", "catalog_linked",
            article_code="8710400417330"),
        row("lidl", "Avocado", "0080616"),
    ]
    matches, blocked, no_proof = service._candidate_plan(items)
    assert len(matches) == 1
    assert matches[0]["source_key"] == ("lidl", "avocado", "0080616")
    assert matches[0]["product_id"] == "avocado"
    assert blocked == no_proof == 0


def test_ah_hv_melk_and_kipfilet_keep_different_product_gtins_separate():
    items = [
        row("ah", "AH HV MELK", "569053", "milk-a", "catalog_linked",
            article_code="8718907056274"),
        row("ah", "AH HV MELK", "92154", "milk-b", "catalog_linked",
            article_code="8710400058519"),
        row("ah", "AH HV MELK", "11943"),
        row("jumbo", "HV MELK JUMBO", "101"),
        row("ah", "AH KIPFILET", "595589", "chicken-a", "catalog_linked",
            article_code="8718907456487"),
        row("ah", "AH KIPFILET", "49900", "chicken-b", "catalog_linked",
            article_code="8718907852555"),
        row("ah", "AH KIPFILET", "805391"),
    ]
    matches, blocked, missing = service._candidate_plan(items)
    assert matches == [] and blocked == 3 and missing == 0


def test_ah_elstar_and_wasmiddel_saved_barcode_still_require_review():
    items = [
        row("ah", "AH ELSTAR", "706911", "elstar", "catalog_linked",
            article_code="8718906836846"),
        row("ah", "AH ELSTAR", "518022", status="saved_only",
            manual_barcode="8718265121195"),
        row("jumbo", "ELSTAR JUMBO", "55"),
        row("ah", "AH WASMIDDEL", "11116", "detergent", "catalog_linked",
            article_code="8718907930239"),
        row("ah", "AH WASMIDDEL", "11118", status="saved_only",
            manual_barcode="8718452775927"),
        row("ah", "AH WASMIDDEL", ""),
    ]
    matches, blocked, missing = service._candidate_plan(items)
    assert matches == [] and blocked == 2 and missing == 0


def test_confirmed_name_alias_applies_to_prefixed_and_suffixed_receipts():
    items = [
        row("ah", "AH HALFVOLLE MELK", "21003", "milk",
            "catalog_linked", article_code="8712345678906"),
        row("ah", "AH HV MELK", "11943"),
        row("jumbo", "HV MELK JUMBO", "0077"),
        row("plus", "HV MELK", "909"),
    ]
    aliases = {"hv melk": {"target_name": "halfvolle melk", "product_id": "milk"}}
    candidates, blocked, without_proof = service._candidate_plan(items, aliases)
    assert {(item["source_key"][0], item["source_key"][2])
            for item in candidates} == {
        ("ah", "11943"), ("jumbo", "0077"), ("plus", "909")
    }
    assert all(item["product_id"] == "milk" for item in candidates)
    assert blocked == without_proof == 0


def test_store_marker_does_not_mask_conflicting_product_destinations():
    # Both labels become "elstar", but the existing Catalogus IDs disagree.
    items = [
        row("ah", "AH ELSTAR", "706911", "elstar-a", "catalog_linked"),
        row("jumbo", "ELSTAR JUMBO", "999", "elstar-b", "catalog_linked"),
        row("lidl", "ELSTAR", "888"),
    ]
    matches, blocked, missing = service._candidate_plan(items)
    assert matches == [] and blocked == 1 and missing == 0
