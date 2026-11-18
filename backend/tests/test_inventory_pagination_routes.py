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
    """The SQL first-screen path returns 10 complete articles, not all rows."""
    from sqlalchemy import create_engine, text

    connection_engine = create_engine("sqlite://")
    with connection_engine.begin() as conn:
        for statement in (
            "CREATE TABLE inventory (id TEXT, naam TEXT, aantal FLOAT, "
            "household_id TEXT, status TEXT, household_article_id TEXT, "
            "space_id TEXT, sublocation_id TEXT)",
            "CREATE TABLE spaces (id TEXT, naam TEXT)",
            "CREATE TABLE sublocations (id TEXT, naam TEXT)",
            "CREATE TABLE household_articles (id TEXT, household_id TEXT, article_group_id TEXT)",
            "CREATE TABLE article_groups (id TEXT, household_id TEXT, name TEXT)",
        ):
            conn.execute(text(statement))
        conn.execute(text("INSERT INTO spaces VALUES ('k', 'Keuken'), ('b', 'Berging')"))
        conn.execute(text("INSERT INTO article_groups VALUES ('g', 'household-1', 'Zuivel')"))
        conn.execute(text(
            "INSERT INTO household_articles VALUES ('milk', 'household-1', 'g')"
        ))
        stock = [
            {"id": "m1", "naam": "Melk", "aantal": 2, "household_id": "household-1",
             "status": "active", "household_article_id": "milk", "space_id": "k",
             "sublocation_id": None},
            {"id": "m2", "naam": "Melk", "aantal": 3, "household_id": "household-1",
             "status": "active", "household_article_id": "milk", "space_id": "b",
             "sublocation_id": None},
        ]
        stock.extend({
            "id": f"z{i:02}", "naam": f"Z-{i:02}", "aantal": 1,
            "household_id": "household-1", "status": "active",
            "household_article_id": None, "space_id": "k", "sublocation_id": None,
        } for i in range(23))
        # Neither an inactive/empty row nor another household may appear.
        stock.extend([
            {"id": "ghost", "naam": "A-ghost", "aantal": 0,
             "household_id": "household-1", "status": "active",
             "household_article_id": None, "space_id": "k", "sublocation_id": None},
            {"id": "foreign", "naam": "A-foreign", "aantal": 10,
             "household_id": "household-2", "status": "active",
             "household_article_id": None, "space_id": "k", "sublocation_id": None},
        ])
        conn.execute(text(
            "INSERT INTO inventory "
            "(id, naam, aantal, household_id, status, household_article_id, space_id, sublocation_id) "
            "VALUES (:id, :naam, :aantal, :household_id, :status, "
            ":household_article_id, :space_id, :sublocation_id)"
        ), stock)

        first = pagination._fast_mobile_page(
            conn, "household-1", page=1, page_size=10, location_tracking_enabled=True,
        )
        assert first["total"] == 24
        assert first["inventory_total"] == 24
        assert len(first["source_rows"]) == 11  # one article has two stock positions
        assert {row["id"] for row in first["source_rows"][:2]} == {"m1", "m2"}
        assert {row["household_article_id"] for row in first["source_rows"][:2]} == {"milk"}
        assert set(first["location_options"]) == {"Keuken", "Meerdere locaties"}
        assert set(first["article_group_options"]) == {"Zuivel", "Niet ingedeeld"}
        assert all(row["id"] not in {"ghost", "foreign"} for row in first["source_rows"])

        second = pagination._fast_mobile_page(
            conn, "household-1", page=2, page_size=10, location_tracking_enabled=False,
        )
        assert len(second["source_rows"]) == 10
        assert second["location_options"] == []
        assert second["total"] == 24
        assert not any(row["household_article_id"] == "milk" for row in second["source_rows"])
        last = pagination._fast_mobile_page(
            conn, "household-1", page=3, page_size=10, location_tracking_enabled=True,
        )
        assert len(last["source_rows"]) == 4
        assert last["total"] == 24
        empty = pagination._fast_mobile_page(
            conn, "household-1", page=4, page_size=10, location_tracking_enabled=True,
        )
        assert not empty["source_rows"]
        assert empty["total"] == 24
    connection_engine.dispose()
