"""PR5: verified household-isolated digital receipt import progress.

No production data, credentials, migrations or receipt writes are used.
"""
from sqlalchemy import create_engine, text

from app.services.retailer_history_progress import load_retailer_history_progress


def _database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as db:
        db.exec_driver_sql(
            "CREATE TABLE household_receipt_history_cutovers "
            "(household_id TEXT PRIMARY KEY, first_current_purchase_date DATE)"
        )
        db.exec_driver_sql(
            "CREATE TABLE raw_receipts (id TEXT PRIMARY KEY, household_id TEXT, "
            "source_id TEXT, deleted_at TEXT, duplicate_of_raw_receipt_id TEXT)"
        )
        db.exec_driver_sql(
            "CREATE TABLE receipt_tables (id TEXT PRIMARY KEY, raw_receipt_id TEXT, "
            "household_id TEXT, deleted_at TEXT, purchase_at DATETIME, "
            "purchase_at_source TEXT, parse_status TEXT)"
        )
        db.exec_driver_sql(
            "CREATE TABLE retailer_import_queue (household_id TEXT, provider TEXT, status TEXT)"
        )
        db.exec_driver_sql(
            "CREATE TABLE maintenance_control (id INTEGER PRIMARY KEY, state TEXT)"
        )
        db.exec_driver_sql(
            "CREATE TABLE platform_feature_flags (flag_key TEXT PRIMARY KEY, enabled BOOLEAN)"
        )
        db.execute(text("INSERT INTO maintenance_control VALUES (1, 'normal')"))
        db.execute(text(
            "INSERT INTO platform_feature_flags VALUES ('retailer_auto_import', 1)"
        ))
        db.execute(text(
            "INSERT INTO household_receipt_history_cutovers VALUES "
            "('home-a', '2026-11-21')"
        ))
    return engine


def _receipt(db, owner, provider, key, purchase_date, source="retailer", status="parsed"):
    db.execute(text("""
        INSERT INTO raw_receipts (id, household_id, source_id)
        VALUES (:id, :owner, :source_id)
    """), {"id": key, "owner": owner, "source_id": f"{owner}-retailer-{provider}"})
    db.execute(text("""
        INSERT INTO receipt_tables
          (id, raw_receipt_id, household_id, purchase_at, purchase_at_source, parse_status)
        VALUES (:id, :id, :owner, :purchase, :source, :status)
    """), {
        "id": "rt-" + key, "owner": owner, "purchase": purchase_date,
        "source": source, "status": status,
    })


def _provider(progress, code):
    return next(item for item in progress["providers"] if item["code"] == code)


def test_progress_uses_original_purchase_date_and_isolates_households():
    engine = _database()
    with engine.begin() as db:
        _receipt(db, "home-a", "ah", "ah-old", "2026-11-20 20:00:00")
        _receipt(db, "home-a", "ah", "ah-current", "2026-11-21 00:00:00")
        _receipt(db, "home-a", "ah", "ah-default", "2026-11-20 08:00:00",
                 source="import_default")
        _receipt(db, "home-a", "jumbo", "jumbo-no-date", None)
        _receipt(db, "home-b", "ah", "other-household", "2026-11-20 12:00:00")
        for owner, provider, state in (
            ("home-a", "lidl", "pending"),
            ("home-a", "lidl", "processing"),
            ("home-a", "lidl", "completed"),
            ("home-a", "jumbo", "review_required"),
            ("home-b", "lidl", "pending"),
        ):
            db.execute(text("""
                INSERT INTO retailer_import_queue VALUES (:owner, :provider, :state)
            """), {"owner": owner, "provider": provider, "state": state})

    result = load_retailer_history_progress(engine, household_id="home-a")
    assert result["history_cutover_enabled"] is True
    assert result["complete_retailer_history_known"] is False
    assert result["coverage"] == "persisted_retailer_receipts_and_queue_only"
    assert result["auto_import_paused"] is False
    assert [entry["code"] for entry in result["providers"]] == ["ah", "lidl", "jumbo"]

    ah = _provider(result, "ah")
    assert ah["saved_receipts"] == ah["kassa_receipts"] == 3
    assert ah["historical_receipts"] == 1
    assert ah["review_receipts"] == 1
    lidl = _provider(result, "lidl")
    assert (lidl["queue_pending"], lidl["queue_processing"],
            lidl["queue_completed"]) == (1, 1, 1)
    assert _provider(result, "jumbo")["queue_review_required"] == 1
    assert _provider(result, "jumbo")["review_receipts"] == 1

    other = load_retailer_history_progress(engine, household_id="home-b")
    assert _provider(other, "ah")["kassa_receipts"] == 1
    assert _provider(other, "ah")["historical_receipts"] is None
    assert _provider(other, "lidl")["queue_pending"] == 1
    assert _provider(other, "lidl")["queue_processing"] == 0
    assert other["history_cutover_enabled"] is False


def test_queue_pause_read_only_does_not_advance_or_discard_anything():
    engine = _database()
    with engine.begin() as db:
        db.execute(text("UPDATE platform_feature_flags SET enabled = 0"))
        db.execute(text("""
            INSERT INTO retailer_import_queue VALUES ('home-a', 'lidl', 'pending')
        """))
    result = load_retailer_history_progress(engine, household_id="home-a")
    assert result["auto_import_paused"] is True
    assert _provider(result, "lidl")["queue_pending"] == 1
    with engine.connect() as db:
        assert db.execute(text("""
            SELECT status FROM retailer_import_queue WHERE household_id='home-a'
        """)).scalar_one() == "pending"


def test_no_unknown_household_or_pseudohistory():
    engine = _database()
    try:
        load_retailer_history_progress(engine, household_id="  ")
    except ValueError as exc:
        assert "huishouden" in str(exc).lower()
    else:
        raise AssertionError("Empty household context cannot yield a history overview")
