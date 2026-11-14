"""Regression contracts: no forbidden transitive or batch synonym group."""
from app.services.article_synonym_service import _manual_pair_conflict
from app.services.synonym_group_safety import prospective_group_conflict
from app.services.synonym_equivalence_review import proven_semantic_conflicts, review_pair


def product(pid, name, gtin="", brick="", codes=(), size="1", unit="l"):
    return {"id": pid, "name": name, "variant": "", "primary_gtin": gtin,
            "brick_code": brick, "article_codes": list(codes),
            "size_value": size, "size_unit": unit}


def check(products, existing, proposed):
    return prospective_group_conflict(
        {p["id"]: p for p in products}, existing, proposed, _manual_pair_conflict,
    )


def test_a_b_c_indirect_milk_fat_contradiction():
    items = [product("a", "Halfvolle melk"), product("b", "Melk"),
             product("c", "Volle melk")]
    assert _manual_pair_conflict(items[0], items[1]) is None
    assert _manual_pair_conflict(items[1], items[2]) is None
    conflict = check(items, {("a", "b")}, {("b", "c")})
    assert conflict["type"] == "transitive_semantic_conflict"
    assert (conflict["left_id"], conflict["right_id"]) == ("a", "c")
    assert "melkvet" in conflict["detail"]


def test_bulk_checks_all_new_connections_together():
    items = [product("a", "Halfvolle melk"), product("b", "Melk"),
             product("c", "Volle melk")]
    assert check(items, set(), {("a", "b"), ("b", "c")})["type"] == "transitive_semantic_conflict"
    assert check(items, set(), {("a", "b")}) is None
    assert check(items, {("a", "b")}, set()) is None


def test_indirect_duplicate_gtin_and_article_code_not_synonyms():
    items = [product("a", "Melk", gtin="08719587325926"), product("b", "Melk"),
             product("c", "Melk", gtin="08719587325926")]
    assert check(items, {("a", "b")}, {("b", "c")})["type"] == "transitive_same_gtin"
    items[0]["primary_gtin"] = items[2]["primary_gtin"] = ""
    items[0]["article_codes"] = items[2]["article_codes"] = ["ah: 123"]
    assert check(items, {("a", "b")}, {("b", "c")})["type"] == "transitive_shared_article_code"


def test_known_different_gpc_is_conflict_across_component():
    items = [product("a", "Melk", brick="10000025"), product("b", "Melk"),
             product("c", "Melk", brick="10000026")]
    assert check(items, {("a", "b")}, {("b", "c")})["type"] == "transitive_gpc_mismatch"
    items[2]["brick_code"] = "10000025"
    assert check(items, {("a", "b")}, {("b", "c")}) is None


def test_only_explicit_semantic_contradictions_count():
    assert "Verschil in lactose" in proven_semantic_conflicts(
        product("a", "Lactosevrije melk"), product("b", "Melk met lactose"))
    assert "Verschillende productsoorten" in proven_semantic_conflicts(
        product("a", "Mayonaise"), product("b", "Melk"))
    assert not proven_semantic_conflicts(product("a", "Melk"), product("b", "Halfvolle melk"))


def test_package_size_difference_is_reviewable_not_banned():
    a, b = product("a", "Burrata", size="125", unit="g"), product("b", "Burrata", size="150", unit="g")
    assert check([a, b], set(), {("a", "b")}) is None
    assert review_pair(a, b)["review_level"] == "check"


def test_missing_member_and_group_limit_fail_closed(monkeypatch):
    assert check([product("a", "Melk"), product("b", "Melk")],
                 {("a", "lost")}, {("a", "b")})["type"] == "missing_article"
    from app.services import synonym_group_safety
    monkeypatch.setattr(synonym_group_safety, "MAX_GROUP_PRODUCTS", 2)
    assert check([product("a", "Melk"), product("b", "Melk"), product("c", "Melk")],
                 {("a", "b")}, {("b", "c")})["type"] == "group_limit"
