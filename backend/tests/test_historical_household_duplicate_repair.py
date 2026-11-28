"""Conservative catalog-only historical household article merge policy."""
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
