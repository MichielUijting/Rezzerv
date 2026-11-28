"""Read-only repair evidence: never silently repair uncertain historical identity."""
from app.services.historical_onboarding_repair_audit import (
    summarize_historical_repair_evidence, prediction_setting_blockers,
)


def _row(*, day, sku="123", name="MELK", article=None, store="lidl"):
    return {
        "source_type": "retailer_api", "source_provider": store,
        "external_article_code": sku, "raw_label": name,
        "matched_article_id": article, "purchase_at": day,
    }


def test_price_change_does_not_hide_split_retailer_identity_candidates():
    articles = {
        "a": {"naam": "Melk", "consumable": True, "global_product_id": None},
        "b": {"naam": "Melk", "consumable": True, "global_product_id": None},
    }
    result = summarize_historical_repair_evidence([
        _row(day="2026-10-01", name="MELK", article="a"),
        _row(day="2026-10-10", name="MELK", article="b"),
    ], articles)
    assert result["repeated_sku_description_groups"] == 1
    assert result["split_sku_description_groups"] == 1
    assert result["household_article_identities_changed"] is False
    assert result["requires_canonical_proof_before_merge"] is True
    assert "123" not in str(result)


def test_same_sku_different_description_is_conflict_not_proven_duplicate():
    articles = {
        "a": {"naam": "Melk", "consumable": True},
        "b": {"naam": "Sap", "consumable": False},
    }
    result = summarize_historical_repair_evidence([
        _row(day="2026-09-01", name="MELK", article="a"),
        _row(day="2026-10-01", name="SAP", article="b"),
    ], articles)
    assert result["split_sku_description_groups"] == 0
    assert result["retailer_sku_description_conflicts"] == 1


def test_catalog_duplicates_and_lack_of_product_link_are_distinguished():
    articles = {
        "a": {"naam": "Melk", "global_product_id": "gp1", "consumable": True},
        "b": {"naam": "Melk", "global_product_id": "gp1", "consumable": True},
        "c": {"naam": "Onbekend", "global_product_id": None, "consumable": False},
    }
    result = summarize_historical_repair_evidence([
        _row(day="2026-10-01", article="a"),
        _row(day="2026-10-04", article=None),
    ], articles)
    assert result["confirmed_catalog_product_duplicate_groups"] == 1
    assert result["unlinked_digital_rows"] == 1


class _Result:
    def __init__(self, rows):
        self.rows = rows
    def mappings(self):
        return self
    def all(self):
        return self.rows


class _Conn:
    def __init__(self, enabled, days):
        self.enabled, self.days = enabled, days
        self.sql = None
    def execute(self, sql, params):
        self.sql = str(sql)
        assert params["household_id"] == "h1"
        return _Result([
            {"setting_key": "almost_out_prediction_enabled",
             "setting_value": self.enabled},
            {"setting_key": "almost_out_prediction_days",
             "setting_value": self.days},
        ])


def test_100_day_horizon_reports_disabled_prediction_without_overwriting():
    conn = _Conn("false", "100")
    result = prediction_setting_blockers(conn, "h1")
    assert result == {
        "prediction_explicitly_stored_disabled": True,
        "prediction_days": 100,
        "prediction_preference_preserved": True,
    }
    assert "SELECT" in conn.sql and "UPDATE" not in conn.sql


def test_enabled_prediction_is_not_reported_as_disabled():
    assert prediction_setting_blockers(_Conn("true", "100"), "h1")[
        "prediction_explicitly_stored_disabled"
    ] is False
