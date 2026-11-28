"""Contract for household-scoped, read-only digital receipt checkpoint dates."""
from datetime import date, datetime, timezone

from app.services.retailer_receipt_import_dates import _iso_date, latest_retailer_import_dates


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeConnection:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def execute(self, query, params):
        sql = str(query)
        self.calls.append((sql, dict(params)))
        assert params["household_id"] == "household-a"
        if "MAX(CAST(rt.purchase_at AS date))" in sql:
            # The Jumbo checkpoint is a confirmed purchase, never upload time.
            assert "JOIN receipt_tables rt" in sql
            assert "rr.household_id = :household_id" in sql
            assert "rt.household_id = :household_id" in sql
            assert "rr.duplicate_of_raw_receipt_id IS NULL" in sql
            assert "rt.purchase_at_source" in sql
            assert "'import_default'" in sql
            assert "'parsed', 'approved'" in sql
            assert params["source_id"] == "household-a-retailer-jumbo"
            return _Scalar(self.responses[params["source_id"]])
        if "MAX(created_at)" in sql:
            assert "household_id = :household_id" in sql
            assert "source_id = :source_id" in sql
            assert "deleted_at IS NULL" in sql
            source_id = params["source_id"]
            assert source_id.startswith("household-a-retailer-")
            return _Scalar(self.responses[source_id])
        assert "household_lidl_import_windows" in sql
        assert "WHERE household_id = :household_id" in sql
        return _Scalar(self.responses["lidl-checkpoint"])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _FakeEngine:
    def __init__(self, results):
        self.connection = _FakeConnection(results)

    def connect(self):
        return self.connection


def test_recent_imports_and_acknowledged_lidl_checkpoint():
    engine = _FakeEngine({
        "household-a-retailer-jumbo": datetime(2026, 10, 22, 15, 4, tzinfo=timezone.utc),
        "household-a-retailer-lidl": date(2026, 10, 19),
        "lidl-checkpoint": date(2026, 10, 21),
    })
    result = latest_retailer_import_dates(engine, household_id="household-a")
    assert result == {"jumbo": "2026-10-22", "lidl": "2026-10-21"}
    assert len(engine.connection.calls) == 3


def test_first_import_stays_null_for_client_previous_year_fallback():
    engine = _FakeEngine({
        "household-a-retailer-jumbo": None,
        "household-a-retailer-lidl": None,
        "lidl-checkpoint": None,
    })
    assert latest_retailer_import_dates(engine, household_id="household-a") == {
        "jumbo": None,
        "lidl": None,
    }


def test_lidl_receipt_date_wins_over_older_scan_checkpoint():
    engine = _FakeEngine({
        "household-a-retailer-jumbo": None,
        "household-a-retailer-lidl": date(2026, 10, 22),
        "lidl-checkpoint": date(2026, 10, 19),
    })
    assert latest_retailer_import_dates(engine, household_id="household-a")["lidl"] == "2026-10-22"


def test_invalid_provider_values_not_exposed():
    assert _iso_date(None) is None
    assert _iso_date("not-a-date") is None
    assert _iso_date("2026-02-30T12:00:00") is None
    assert _iso_date(date(2026, 10, 19)) == "2026-10-19"


def test_jumbo_purchase_checkpoint_is_inclusive_and_not_upload_day():
    # The query does not use raw_receipts.created_at, which can be weeks later.
    engine = _FakeEngine({
        "household-a-retailer-jumbo": date(2026, 8, 19),
        "household-a-retailer-lidl": None,
        "lidl-checkpoint": None,
    })
    result = latest_retailer_import_dates(engine, household_id="household-a")
    assert result["jumbo"] == "2026-08-19"
    jumbo_sql = engine.connection.calls[0][0]
    assert "MAX(CAST(rt.purchase_at AS date))" in jumbo_sql
    assert "MAX(created_at)" not in jumbo_sql
    assert "rr.source_id = :source_id" in jumbo_sql
