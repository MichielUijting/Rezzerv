"""Conservative central catalog or independently verified source GTIN policy."""
from app.services.historical_household_duplicate_repair import _comparable, UnsafeHistoricalMerge


def make_record(**kw):
    return {
        "global_product_id": "catalog-1", "barcode": None,
        "custom_name": None, "article_group_id": None,
        "default_inventory_handling": "STOCK", "consumable": None,
        "min_stock": None, "ideal_stock": None,
        **kw,
    }


def test_only_confirmed_catalog_identity_may_be_considered():
    assert _comparable(make_record(), make_record()) is True
    assert _comparable(make_record(), make_record(global_product_id="catalog-2")) is False
    assert _comparable(make_record(), make_record(global_product_id=None)) is False


def test_manual_settings_and_barcode_conflicts_block_merge():
    first = make_record()
    assert not _comparable(first, make_record(custom_name="Mijn afwijkende product"))
    assert not _comparable(first, make_record(article_group_id="manual-group"))
    assert not _comparable(first, make_record(min_stock=3))
    assert not _comparable(first, make_record(barcode="8712345678901"))
    assert not _comparable(make_record(consumable=False), make_record(consumable=True))
    assert not _comparable(make_record(default_inventory_handling="STOCK"),
                           make_record(default_inventory_handling="DIRECT_CONSUMPTION"))


def test_identical_explicit_product_attributes_do_not_block():
    first = make_record(custom_name="Houdbaar", min_stock=2, consumable=True)
    second = make_record(custom_name="Houdbaar", min_stock=2, consumable=True)
    assert _comparable(first, second)


def test_uncataloged_merge_needs_independent_verified_gtin():
    first = make_record(global_product_id=None, barcode=None)
    second = make_record(global_product_id=None, barcode=None)
    proof = "04006381333931"
    assert not _comparable(first, second)
    assert _comparable(first, second, trusted_gtin=proof)
    assert not _comparable(first, make_record(global_product_id="catalog-1"), trusted_gtin=proof)
    assert not _comparable(first, make_record(global_product_id=None, min_stock=2), trusted_gtin=proof)
    assert not _comparable(first, make_record(global_product_id=None, barcode="5901234123457"), trusted_gtin=proof)
    assert _comparable(first, make_record(global_product_id=None, barcode="4006381333931"), trusted_gtin=proof)


def test_verified_gtin_requires_household_bound_independent_sources_and_no_conflict():
    from app.services.historical_verified_receipt_gtin import verified_uncataloged_groups

    class Result:
        def __init__(self, rows):
            self.rows = rows
        def mappings(self):
            return self
        def all(self):
            return self.rows

    class Connection:
        def __init__(self, rows):
            self.rows = rows
        def execute(self, stmt, params):
            sql = str(stmt)
            assert "rt.household_id=:household_id" in sql
            assert "rs.source_path IN ('ah','jumbo')" in sql
            assert params["household_id"] == "first"
            return Result(self.rows)

    articles = [
        {"id": "a", "global_product_id": None, "barcode": None},
        {"id": "b", "global_product_id": None, "barcode": None},
        {"id": "foreign", "global_product_id": "catalog", "barcode": None},
    ]
    evidence = [
        {"matched_article_id": "a", "barcode": "4006381333931",
         "matched_global_product_id": None, "source_path": "ah"},
        {"matched_article_id": "b", "barcode": "4006381333931",
         "matched_global_product_id": None, "source_path": "jumbo"},
    ]
    assert verified_uncataloged_groups(
        Connection(evidence), household_id="first", cutoff="2026-11-28",
        articles=articles,
    ) == [(articles[:2], "04006381333931")]
    conflicting = [*evidence, {**evidence[-1], "barcode": "5901234123457"}]
    assert verified_uncataloged_groups(
        Connection(conflicting), household_id="first", cutoff="2026-11-28",
        articles=articles,
    ) == []
    unverified = [*evidence[:-1], {**evidence[-1], "barcode": "4006381333930"}]
    assert verified_uncataloged_groups(
        Connection(unverified), household_id="first", cutoff="2026-11-28",
        articles=articles,
    ) == []
