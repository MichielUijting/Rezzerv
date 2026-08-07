from sqlalchemy import create_engine, text

from app.services.household_article_identity_migration_service import (
    migrate_household_article_identities,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT NOT NULL, naam TEXT)"))
        conn.execute(text("CREATE TABLE purchase_import_batches (id TEXT PRIMARY KEY, household_id TEXT NOT NULL)"))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                matched_household_article_id TEXT,
                suggested_household_article_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE store_import_memory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                matched_household_article_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                household_article_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                inventory_id TEXT,
                household_article_id TEXT
            )
        """))
    return engine


def test_unique_live_value_migrates_and_second_run_is_idempotent():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO household_articles VALUES ('ha-1', 'hh-1', 'Volkoren pasta')"))
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch-1', 'hh-1')"))
        conn.execute(text("INSERT INTO purchase_import_lines VALUES ('line-1', 'batch-1', 'live::  volkoren   PASTA ', NULL)"))

    first = migrate_household_article_identities(engine, dry_run=False)
    assert first.migrated == 1
    assert first.unresolved == 0
    assert first.ambiguous == 0

    with engine.begin() as conn:
        value = conn.execute(text("SELECT matched_household_article_id FROM purchase_import_lines WHERE id='line-1'" )).scalar_one()
    assert value == "ha-1"

    second = migrate_household_article_identities(engine, dry_run=False)
    assert second.migrated == 0
    assert second.already_canonical == 1


def test_ambiguous_name_is_reported_and_not_changed():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO household_articles VALUES ('ha-1', 'hh-1', 'Melk')"))
        conn.execute(text("INSERT INTO household_articles VALUES ('ha-2', 'hh-1', ' melk ')"))
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch-1', 'hh-1')"))
        conn.execute(text("INSERT INTO purchase_import_lines VALUES ('line-1', 'batch-1', 'live::Melk', NULL)"))

    report = migrate_household_article_identities(engine, dry_run=False)
    assert report.ambiguous == 1
    assert report.migrated == 0
    with engine.begin() as conn:
        value = conn.execute(text("SELECT matched_household_article_id FROM purchase_import_lines WHERE id='line-1'" )).scalar_one()
    assert value == "live::Melk"


def test_match_never_crosses_household_boundary():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO household_articles VALUES ('ha-2', 'hh-2', 'Mosterd')"))
        conn.execute(text("INSERT INTO purchase_import_batches VALUES ('batch-1', 'hh-1')"))
        conn.execute(text("INSERT INTO purchase_import_lines VALUES ('line-1', 'batch-1', 'live::Mosterd', NULL)"))

    report = migrate_household_article_identities(engine, dry_run=False)
    assert report.unresolved == 1
    assert report.migrated == 0


def test_dry_run_reports_migration_without_writing():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO household_articles VALUES ('ha-1', 'hh-1', 'Yoghurt')"))
        conn.execute(text("INSERT INTO inventory VALUES ('inv-1', 'hh-1', 'live::Yoghurt')"))

    report = migrate_household_article_identities(engine, dry_run=True)
    assert report.migrated == 1
    with engine.begin() as conn:
        value = conn.execute(text("SELECT household_article_id FROM inventory WHERE id='inv-1'" )).scalar_one()
    assert value == "live::Yoghurt"
