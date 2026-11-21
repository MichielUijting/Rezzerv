"""PR3: read-only evidence, household mode, and no manual receipt approval."""
from datetime import date

from app.services import historical_household_stock_source as source

CUTOFF = date(2026, 11, 20)


class Rows:
    def __init__(self, values=None, value=None):
        self.values = values or []
        self.value = value

    def mappings(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.value


class Conn:
    def __init__(self, receipts, *, mode="consume_all_existing_before_purchase",
                 overrides=None, consumable=1):
        self.receipts = receipts
        self.queries = []
        self.consumable = consumable
        self.settings = [
            {"setting_key": "consumable_auto_deduction_mode", "setting_value": mode}
        ]
        if overrides is not None:
            import json
            self.settings.append({
                "setting_key": "article_auto_consume_overrides",
                "setting_value": json.dumps(overrides),
            })

    def execute(self, stmt, args=None):
        sql = str(stmt)
        self.queries.append((sql, args))
        assert sql.lstrip().upper().startswith("SELECT"), sql
        if "FROM household_receipt_history_cutovers" in sql:
            return Rows(value=CUTOFF)
        if "FROM receipt_tables rt" in sql:
            return Rows(self.receipts)
        if "FROM household_articles ha" in sql:
            return Rows([{
                "id": "ha-1", "naam": "Melk", "global_product_id": "gp-1",
                "consumable": self.consumable, "default_inventory_handling": "STOCK",
                "global_product_status": "active", "size_value": 1,
                "size_unit": "l",
            }])
        if "FROM household_settings" in sql:
            return Rows(self.settings)
        raise AssertionError("Unexpected SQL: " + sql)


def line(day, receipt, quantity, *, matched="ha-1", product="gp-1",
         role="product", unit="stuk", status="matched"):
    return {
        "receipt_table_id": receipt, "purchase_at": day,
        "purchase_at_source": "detected", "store_name": "Lidl",
        "sha256_hash": "sha-" + receipt,
        "line_id": receipt + "-1", "line_role": role,
        "inventory_eligible": role == "product",
        "article_match_status": status,
        "matched_article_id": matched,
        "matched_global_product_id": product,
        "quantity": quantity, "unit": unit,
        "product_id": product, "product_status": "active",
        "explicit_household_article_id": matched,
        "article_product_id": "gp-1",
        "article_status": "active",
    }


def test_unapproved_parsed_historical_receipts_are_usable_without_kassa_approval():
    sql = source._HISTORICAL_AUTO_SOURCE_SQL
    assert "rt.approved_at IS NOT NULL" not in sql
    assert "rt.parse_status" in sql
    conn = Conn([
        line("2026-11-01", "a", 2),
        line("2026-11-17", "b", 5),
    ])
    result = source.load_automatic_historical_stock(conn, household_id="home")
    assert result["status"] == "calculated"
    assert result["quantities"] == {"ha-1": 5}
    assert result["writes_inventory"] is False
    assert all(query.startswith("SELECT") for query, _ in conn.queries)
    assert conn.queries[1][1]["household_id"] == "home"


def test_article_override_and_consumable_precedence():
    rows = [
        line("2026-11-01", "a", 3),
        line("2026-11-15", "b", 4),
    ]
    for case, expected in (
        (Conn(rows, mode="none", overrides={"ha-1": "consume_all_existing_before_purchase"}), 4),
        (Conn(rows, mode="consume_all_existing_before_purchase",
              overrides={"ha-1": "none"}), 7),
        (Conn(rows, mode="consume_all_existing_before_purchase",
              overrides={"ha-1": "always_on"}), 4),
        (Conn(rows, mode="consume_all_existing_before_purchase", consumable=0), 7),
    ):
        result = source.load_automatic_historical_stock(case, household_id="home")
        assert result["quantities"]["ha-1"] == expected


def test_confirmed_catalog_product_match_can_resolve_unique_household_article():
    first = line("2026-11-01", "a", 2, matched=None, status="product_matched")
    second = line("2026-11-10", "b", 4, matched=None, status="product_matched")
    conn = Conn([first, second])
    result = source.load_automatic_historical_stock(conn, household_id="home")
    assert result["quantities"] == {"ha-1": 4}


def test_foreign_article_match_invalid_unit_and_nonphysical_are_excluded():
    rows = [
        line("2026-11-01", "a", 1, matched="foreign"),
        line("2026-11-02", "b", 2, role="financial"),
        line("2026-11-03", "c", 100, unit="ml"),
        line("2026-11-04", "d", 1, status="unmatched"),
        line("2026-11-05", "e", 3),
    ]
    result = source.load_automatic_historical_stock(Conn(rows), household_id="home")
    assert result["excluded_untrusted_rows"] == 4
    assert result["quantities"] == {"ha-1": 3}


def test_unknown_household_or_cross_household_not_resolved():
    conn = Conn([])
    try:
        source.load_automatic_historical_stock(conn, household_id="0")
    except ValueError:
        pass
    else:
        raise AssertionError("System household must never inherit stock")
    assert conn.queries == []
