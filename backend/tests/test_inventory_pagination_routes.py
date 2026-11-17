"""Mobile stock pagination: identity, location, filtering, GPC and page boundaries."""
from app.api.inventory_pagination_routes import _group_rows, _project_page


def _stock(id, household_article_id=None, name="Melk", quantity=1, location="Keuken",
           group="Zuivel", brick=""):
    return {
        "id": id,
        "household_article_id": household_article_id,
        "artikel": name,
        "aantal": quantity,
        "locatie": location,
        "sublocatie": "",
        "article_group_name": group,
        "gpc_brick_name": brick,
    }


def test_complete_household_article_is_on_single_page_even_when_stock_has_many_locations():
    rows = [_stock("a1", "a", quantity=2), _stock("a2", "a", quantity=3, location="Berging")]
    rows.extend(_stock(f"b{i}", f"art{i}", f"Z-item {i}") for i in range(23))
    page_one = _project_page(rows, page=1, page_size=10)
    assert page_one["total"] == 24
    assert len(_group_rows(rows)) == 24
    assert len(page_one["source_rows"]) == 11
    assert {r["id"] for r in page_one["source_rows"][:2]} == {"a1", "a2"}
    page_two = _project_page(rows, page=2, page_size=10)
    assert len(_group_rows(page_two["source_rows"])) == 10
    assert not any(r["household_article_id"] == "a" for r in page_two["source_rows"])


def test_unlinked_same_name_rows_remain_separate_identities():
    rows = [_stock("one"), _stock("two")]
    data = _project_page(rows)
    assert data["total"] == 2
    assert len(data["source_rows"]) == 2


def test_filtered_location_and_group_preserve_total_and_full_options():
    rows = [
        _stock("a1", "a", name="Melk", location="Keuken", group="Zuivel"),
        _stock("b1", "b", name="Rijst", location="Berging", group="Granen"),
        _stock("c1", "c", name="Olie", location="Keuken", group="Olie"),
    ]
    data = _project_page(rows, location_filter="Keuken", group_filter="Zuivel")
    assert data["total"] == 1
    assert data["inventory_total"] == 3
    assert len(data["source_rows"]) == 1
    assert set(data["location_options"]) == {"Berging", "Keuken"}
    assert set(data["article_group_options"]) == {"Granen", "Olie", "Zuivel"}


def test_search_across_page_uses_gpc_or_group_not_just_current_page():
    rows = [_stock(f"x{i}", str(i), name=f"Artikel {i}", group="Overig") for i in range(26)]
    result = _project_page(rows, query="special", gpc_map={"25": {"gpc_family_name": "Special"}})
    assert result["total"] == 1
    assert result["source_rows"][0]["id"] == "x25"


def test_zero_stock_removed_before_pagination_and_disabled_location_filter():
    rows = [_stock("a", "a", quantity=0), _stock("b", "b", location="Keuken")]
    result = _project_page(rows, location_filter="Andere", location_tracking_enabled=False)
    assert result["total"] == 1
    assert result["location_options"] == []


def test_name_desc_sorts_entire_data_before_slicing():
    rows = [_stock(str(i), str(i), name=f"Artikel {i:02d}") for i in range(21)]
    page = _project_page(rows, page=2, sort_key="name-desc", page_size=10)
    assert len(page["source_rows"]) == 10
    assert page["source_rows"][0]["id"] == "10"
