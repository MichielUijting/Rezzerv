"""No-SQLite identity contracts: only confirmed connected Catalogus components."""
from app.services.synonym_auto_consume_identity import confirmed_household_synonym_group


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Fake:
    def __init__(self):
        self.products = {name: "active" for name in "ABCD"}
        self.links = [("A", "B"), ("B", "C")]
        self.articles = [
            {"id": "a", "household_id": "h1", "global_product_id": "A", "status": "active"},
            {"id": "b", "household_id": "h1", "global_product_id": "B", "status": "active"},
            {"id": "c", "household_id": "h1", "global_product_id": "C", "status": "active"},
            {"id": "b-other", "household_id": "h2", "global_product_id": "B", "status": "active"},
        ]

    def execute(self, statement, params):
        sql = str(statement)
        if "SELECT ha.global_product_id" in sql:
            return _Rows([{"global_product_id": article["global_product_id"]}
                for article in self.articles if article["id"] == params["article_id"]
                and article["household_id"] == params["household_id"]
                and article["status"] == "active"
                and self.products.get(article["global_product_id"]) == "active"])
        if "WITH RECURSIVE connected" in sql:
            component = {params["catalog_id"]}
            while True:
                expanded = component | {other for a, b in self.links
                    for x, other in ((a, b), (b, a)) if x in component}
                if expanded == component:
                    break
                component = expanded
            return _Rows([{
                "product_id": product, "existing_product_id": product if product in self.products else None,
                "catalog_status": self.products.get(product)
            } for product in sorted(component)])
        if "ha.global_product_id = ANY(:catalog_ids)" in sql:
            return _Rows([{"id": a["id"], "global_product_id": a["global_product_id"]}
                for a in self.articles if a["household_id"] == params["household_id"]
                and a["status"] == "active" and a["global_product_id"] in params["catalog_ids"]])
        raise AssertionError("unexpected database query: " + sql[:150])


def test_three_member_chain_resolves_for_each_purchased_member():
    db = _Fake()
    for article in ("a", "b", "c"):
        assert confirmed_household_synonym_group(db, "h1", article) == ("a", "b", "c")


def test_multiple_paths_and_cycles_do_not_duplicate_members():
    db = _Fake()
    db.links += [("A", "C"), ("C", "A"), ("B", "A")]
    assert confirmed_household_synonym_group(db, "h1", "b") == ("a", "b", "c")


def test_missing_household_representation_can_be_skipped_without_making_up_identity():
    db = _Fake()
    db.articles = [a for a in db.articles if a["id"] != "c"]
    assert confirmed_household_synonym_group(db, "h1", "a") == ("a", "b")


def test_no_auto_link_from_name_or_unconfirmed_proposal():
    db = _Fake()
    db.links = []
    assert confirmed_household_synonym_group(db, "h1", "a") == ("a",)


def test_cross_household_stock_never_joins_group():
    db = _Fake()
    assert confirmed_household_synonym_group(db, "h2", "b-other") == ("b-other",)
    assert confirmed_household_synonym_group(db, "h2", "a") == ("a",)


def test_duplicate_household_representation_disables_group():
    db = _Fake()
    db.articles.append({"id": "a-duplicate", "household_id": "h1",
                        "global_product_id": "A", "status": "active"})
    assert confirmed_household_synonym_group(db, "h1", "b") == ("b",)


def test_inactive_product_anywhere_in_component_disables_group():
    db = _Fake()
    db.products["C"] = "inactive"
    assert confirmed_household_synonym_group(db, "h1", "a") == ("a",)


def test_unlinked_original_article_disables_group():
    db = _Fake()
    db.articles[0]["global_product_id"] = None
    assert confirmed_household_synonym_group(db, "h1", "a") == ("a",)


def test_group_limit_fails_closed(monkeypatch):
    from app.services import synonym_auto_consume_identity as identity
    db = _Fake()
    monkeypatch.setattr(identity, "MAX_GROUP_PRODUCTS", 2)
    assert confirmed_household_synonym_group(db, "h1", "a") == ("a",)
