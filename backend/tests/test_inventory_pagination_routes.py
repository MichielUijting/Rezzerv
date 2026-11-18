"""Mobile stock pagination: identity, location, filtering, GPC and page boundaries."""
from app.api.inventory_pagination_routes import _group_rows, _project_page
import app.api.inventory_pagination_routes as pagination
from types import SimpleNamespace


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



def test_initial_mobile_page_does_not_compute_unused_gpc(monkeypatch):
    """A first-screen GET must not call the heavyweight GPC classifier."""
    stock = [_stock("stock-1", "article-1", name="Melk", quantity=2)]

    class Connection:
        def execute(self, statement, parameters):
            assert parameters == {"household_id": "household-1"}
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: stock))

    class ContextManager:
        def __enter__(self):
            return Connection()

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(
        pagination, "engine", SimpleNamespace(connect=lambda: ContextManager()),
    )

    def forbidden_projection(*_args, **_kwargs):
        raise AssertionError("GPC projection is not needed on the first page")

    monkeypatch.setattr(pagination, "dutch_gpc_by_household_article", forbidden_projection)

    from app import main as legacy
    monkeypatch.setattr(legacy, "require_household_context", lambda _auth: object())
    monkeypatch.setattr(
        legacy, "household_context_from_runtime_context",
        lambda _ctx: SimpleNamespace(active_household_id="household-1"),
    )
    result = pagination.mobile_inventory_page(
        page=1, page_size=10, query="", location_filter="", group_filter="",
        sort_key="name-asc", location_tracking_enabled=True,
        authorization="Bearer test",
    )
    assert result["total"] == 1
    assert len(result["rows"]) == 1
    assert result["rows"][0]["household_article_id"] == "article-1"
    assert result["rows"][0]["gpc_brick_name"] == ""




def test_fast_page_only_reads_stock_rows_for_visible_identities():
    """Prove the page query is bounded and tenant-scoped without test DB setup."""
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def scalars(self):
            return self

        def all(self):
            return self.rows

    group_meta = [
        {"identity_key": "household:milk", "location_count": 2,
         "single_location": "Berging", "article_group": "Zuivel"},
    ] + [
        {"identity_key": f"inventory:z{i:02}", "location_count": 1,
         "single_location": "Keuken", "article_group": "Niet ingedeeld"}
        for i in range(23)
    ]
    identities = [item["identity_key"] for item in group_meta]
    detail_rows = [
        {"id": "m1", "artikel": "Melk", "aantal": 2,
         "household_article_id": "milk", "locatie": "Keuken"},
        {"id": "m2", "artikel": "Melk", "aantal": 3,
         "household_article_id": "milk", "locatie": "Berging"},
    ] + [
        {"id": f"z{i:02}", "artikel": f"Z-{i:02}", "aantal": 1,
         "household_article_id": None, "locatie": "Keuken"}
        for i in range(23)
    ]

    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            sql = str(statement)
            self.calls.append((sql, params))
            assert params["household_id"] == "household-1"
            assert "COALESCE(i.aantal, 0) > 0" in sql
            assert "i.household_id = :household_id" in sql
            if "GROUP BY" in sql:
                assert "COUNT(DISTINCT" in sql
                return Result(group_meta)
            if "WITH ranked AS" in sql:
                assert "ROW_NUMBER() OVER" in sql
                assert "PARTITION BY" in sql
                assert "LIMIT :page_size OFFSET :offset" in sql
                offset = params["offset"]
                return Result(identities[offset:offset + params["page_size"]])
            assert "identity_keys" in params
            assert "IN (__[POSTCOMPILE_identity_keys])" in sql
            allowed = set(params["identity_keys"])
            assert len(allowed) <= 10
            rows = [
                row for row in detail_rows
                if ("household:" + row["household_article_id"] if row["household_article_id"]
                    else "inventory:" + row["id"]) in allowed
            ]
            return Result(rows)

    conn = Connection()
    first = pagination._fast_mobile_page(
        conn, "household-1", page=1, page_size=10,
        location_tracking_enabled=True,
    )
    assert first["total"] == 24
    assert first["inventory_total"] == 24
    assert len(first["source_rows"]) == 11
    assert {row["id"] for row in first["source_rows"][:2]} == {"m1", "m2"}
    assert set(first["location_options"]) == {"Keuken", "Meerdere locaties"}
    assert set(first["article_group_options"]) == {"Zuivel", "Niet ingedeeld"}
    assert len(conn.calls) == 3
    assert len(conn.calls[2][1]["identity_keys"]) == 10

    second = pagination._fast_mobile_page(
        conn, "household-1", page=2, page_size=10,
        location_tracking_enabled=False,
    )
    assert len(second["source_rows"]) == 10
    assert second["location_options"] == []
    assert all(row["household_article_id"] is None for row in second["source_rows"])

    last = pagination._fast_mobile_page(
        conn, "household-1", page=3, page_size=10,
        location_tracking_enabled=True,
    )
    assert len(last["source_rows"]) == 4
    empty = pagination._fast_mobile_page(
        conn, "household-1", page=4, page_size=10,
        location_tracking_enabled=True,
    )
    assert empty["source_rows"] == []
    assert empty["total"] == 24
    assert len(conn.calls) == 11  # no physical stock fetch for an empty page
