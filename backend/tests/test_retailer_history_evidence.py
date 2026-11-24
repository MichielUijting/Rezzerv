"""Read-only, household-isolated receipt provenance for the onboarding counter."""
from datetime import datetime

import pytest

from app.services.retailer_history_progress import load_retailer_history_evidence


class _Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _ReadOnlyConnection:
    def __init__(self):
        self.queries = []

    def execute(self, statement, params):
        sql = str(statement)
        self.queries.append((sql, dict(params)))
        assert sql.lstrip().startswith("SELECT")
        assert "rr.household_id = :household_id" in sql
        assert "rt.household_id = :household_id" in sql
        assert "rr.source_id = :source_id" in sql
        assert "rr.deleted_at IS NULL" in sql
        assert "rt.deleted_at IS NULL" in sql
        assert "rr.duplicate_of_raw_receipt_id IS NULL" in sql
        assert "LIMIT :limit" in sql
        assert params["household_id"] == "household-1"
        assert params["source_id"] == "household-1-retailer-ah"
        return _Rows([{
            "purchase_at": datetime(2026, 9, 8),
            "purchase_at_source": "ah_original",
            "created_at": datetime(2026, 11, 24),
            "parse_status": "parsed",
            "approved_at": None,
            "line_count": 3,
            "id": "secret-internal-id",
            "raw_access_token": "must-not-leak",
        }])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _ReadOnlyEngine:
    def __init__(self):
        self.conn = _ReadOnlyConnection()

    def connect(self):
        return self.conn


def test_history_evidence_is_read_only_household_scoped_and_minimal():
    engine = _ReadOnlyEngine()
    result = load_retailer_history_evidence(
        engine, household_id="household-1", provider="ah",
    )
    assert result["provider"] == "ah"
    assert result["coverage"] == "most_recent_persisted_receipt_records_only"
    assert result["items"] == [{
        "purchase_date": "2026-09-08",
        "received_date": "2026-11-24",
        "purchase_date_source": "ah_original",
        "parse_status": "parsed",
        "line_count": 3,
        "approved": False,
    }]
    assert "secret" not in str(result)
    assert len(engine.conn.queries) == 1


@pytest.mark.parametrize("household,provider", [
    ("", "ah"), ("household-1", ""), ("household-1", "untrusted"),
])
def test_invalid_request_fails_before_database_access(household, provider):
    engine = _ReadOnlyEngine()
    with pytest.raises(ValueError):
        load_retailer_history_evidence(engine, household_id=household, provider=provider)
    assert engine.conn.queries == []


def test_requested_limit_is_capped_to_ten():
    engine = _ReadOnlyEngine()
    load_retailer_history_evidence(engine, household_id="household-1", provider="ah", limit=1000)
    assert engine.conn.queries[0][1]["limit"] == 10
