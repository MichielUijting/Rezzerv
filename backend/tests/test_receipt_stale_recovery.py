from pathlib import Path

from sqlalchemy import create_engine, text

from app.services import receipt_stale_recovery_service as recovery


def _engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                original_filename TEXT,
                mime_type TEXT,
                storage_path TEXT,
                sha256_hash TEXT,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL,
                household_id TEXT,
                parse_status TEXT,
                line_count INTEGER DEFAULT 0,
                approved_at DATETIME,
                reviewed_at DATETIME,
                corrected_by_user_email TEXT,
                totals_overridden INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                corrected_raw_label TEXT,
                corrected_quantity NUMERIC,
                corrected_unit TEXT,
                corrected_unit_price NUMERIC,
                corrected_line_total NUMERIC,
                matched_article_id TEXT,
                matched_global_product_id TEXT,
                is_deleted INTEGER DEFAULT 0,
                is_validated INTEGER DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                source_type TEXT,
                source_reference TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                source_reference TEXT
            )
        """))
    return engine


def _insert_receipt(engine, tmp_path: Path, receipt_id: str, **flags):
    raw_id = f"raw-{receipt_id}"
    source_path = tmp_path / f"{receipt_id}.jpg"
    source_path.write_bytes(b"raw")
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO raw_receipts (
                    id, household_id, original_filename, mime_type,
                    storage_path, sha256_hash, deleted_at
                ) VALUES (
                    :id, '1', :filename, 'image/jpeg',
                    :storage_path, :sha, :deleted_at
                )
            """),
            {
                "id": raw_id,
                "filename": source_path.name,
                "storage_path": str(source_path),
                "sha": f"sha-{receipt_id}",
                "deleted_at": flags.get("raw_deleted_at"),
            },
        )
        conn.execute(
            text("""
                INSERT INTO receipt_tables (
                    id, raw_receipt_id, household_id, parse_status, line_count,
                    approved_at, reviewed_at, corrected_by_user_email,
                    totals_overridden, deleted_at
                ) VALUES (
                    :id, :raw_id, '1', :parse_status, 1,
                    :approved_at, :reviewed_at, :corrected_by_user_email,
                    :totals_overridden, :deleted_at
                )
            """),
            {
                "id": receipt_id,
                "raw_id": raw_id,
                "parse_status": flags.get("parse_status", "review_needed"),
                "approved_at": flags.get("approved_at"),
                "reviewed_at": flags.get("reviewed_at"),
                "corrected_by_user_email": flags.get("corrected_by_user_email"),
                "totals_overridden": flags.get("totals_overridden", 0),
                "deleted_at": flags.get("deleted_at"),
            },
        )
        conn.execute(
            text("""
                INSERT INTO receipt_table_lines (
                    id, receipt_table_id, corrected_raw_label, corrected_quantity,
                    corrected_unit, corrected_unit_price, corrected_line_total,
                    matched_article_id, matched_global_product_id,
                    is_deleted, is_validated
                ) VALUES (
                    :id, :receipt_table_id, :corrected_raw_label, NULL,
                    NULL, NULL, NULL,
                    :matched_article_id, :matched_global_product_id,
                    :is_deleted, :is_validated
                )
            """),
            {
                "id": f"line-{receipt_id}",
                "receipt_table_id": receipt_id,
                "corrected_raw_label": flags.get("corrected_raw_label"),
                "matched_article_id": flags.get("matched_article_id"),
                "matched_global_product_id": flags.get("matched_global_product_id"),
                "is_deleted": flags.get("is_deleted", 0),
                "is_validated": flags.get("is_validated", 0),
            },
        )
        if flags.get("purchase_batch"):
            conn.execute(
                text("INSERT INTO purchase_import_batches (id, source_type, source_reference) VALUES (:id, 'receipt', :source_reference)"),
                {"id": f"batch-{receipt_id}", "source_reference": f"receipt:{receipt_id}"},
            )
        if flags.get("inventory_event"):
            conn.execute(
                text("INSERT INTO inventory_events (id, source_reference) VALUES (:id, :source_reference)"),
                {"id": f"event-{receipt_id}", "source_reference": f"receipt:{receipt_id}"},
            )


def test_candidate_selection_is_fail_closed_for_user_and_business_state(tmp_path):
    engine = _engine()
    _insert_receipt(engine, tmp_path, "safe")
    _insert_receipt(engine, tmp_path, "corrected", corrected_raw_label="user edit")
    _insert_receipt(engine, tmp_path, "validated", is_validated=1)
    _insert_receipt(engine, tmp_path, "matched", matched_article_id="article-1")
    _insert_receipt(engine, tmp_path, "approved", approved_at="2026-08-19 12:00:00")
    _insert_receipt(engine, tmp_path, "reviewed", reviewed_at="2026-08-19 12:00:00")
    _insert_receipt(engine, tmp_path, "override", totals_overridden=1)
    _insert_receipt(engine, tmp_path, "batch", purchase_batch=True)
    _insert_receipt(engine, tmp_path, "inventory", inventory_event=True)
    _insert_receipt(engine, tmp_path, "deleted", deleted_at="2026-08-19 12:00:00")
    _insert_receipt(engine, tmp_path, "already-approved", parse_status="approved")

    candidates = recovery.list_safe_stale_receipt_candidates(engine)
    assert [item["receipt_table_id"] for item in candidates] == ["safe"]
    assert candidates[0]["previous_line_count"] == 1
    assert candidates[0]["mime_type"] == "image/jpeg"


def test_candidate_selection_fails_closed_when_safety_schema_is_missing():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE raw_receipts (id TEXT PRIMARY KEY, storage_path TEXT, deleted_at DATETIME)"))
        conn.execute(text("CREATE TABLE receipt_tables (id TEXT PRIMARY KEY, raw_receipt_id TEXT, parse_status TEXT, deleted_at DATETIME)"))
        conn.execute(text("CREATE TABLE receipt_table_lines (id TEXT PRIMARY KEY, receipt_table_id TEXT)"))

    assert recovery.list_safe_stale_receipt_candidates(engine) == []


def test_recovery_replaces_only_when_preview_is_controlled(tmp_path, monkeypatch):
    engine = _engine()
    _insert_receipt(engine, tmp_path, "safe")
    _insert_receipt(engine, tmp_path, "touched", is_validated=1)

    calls = []

    def fake_preview(candidate):
        assert candidate["receipt_table_id"] == "safe"
        return {
            "is_receipt": True,
            "parse_status": "approved",
            "kassa_status": "Gecontroleerd",
            "failed_criteria": [],
            "line_count": 4,
            "total_amount": 12.24,
        }

    def fake_reparse(_engine, _storage_root, receipt_table_id):
        calls.append(receipt_table_id)
        return {
            "receipt_table_id": receipt_table_id,
            "parse_status": "approved",
            "line_count": 4,
            "deleted": False,
        }

    monkeypatch.setattr(recovery, "_preview_candidate", fake_preview)
    monkeypatch.setattr(recovery, "reparse_receipt", fake_reparse)
    receipt_storage_root = tmp_path / "data" / "receipts" / "raw"
    receipt_storage_root.mkdir(parents=True)

    report = recovery.run_safe_stale_receipt_recovery(engine, receipt_storage_root)
    assert report["status"] == "completed"
    assert report["candidate_count"] == 1
    assert report["reparsed_count"] == 1
    assert report["approved_count"] == 1
    assert report["skipped_not_improved_count"] == 0
    assert report["results"][0]["previous_line_count"] == 1
    assert report["results"][0]["preview_line_count"] == 4
    assert calls == ["safe"]

    second = recovery.run_safe_stale_receipt_recovery(engine, receipt_storage_root)
    assert second["migration_id"] == recovery.MIGRATION_ID
    assert calls == ["safe"]


def test_recovery_does_not_replace_when_preview_still_needs_review(tmp_path, monkeypatch):
    engine = _engine()
    _insert_receipt(engine, tmp_path, "still-review")
    calls = []

    monkeypatch.setattr(
        recovery,
        "_preview_candidate",
        lambda _candidate: {
            "is_receipt": True,
            "parse_status": "review_needed",
            "kassa_status": "Controle nodig",
            "failed_criteria": ["LINE_SUM_TOTAL_MISMATCH"],
            "line_count": 3,
            "total_amount": 12.24,
        },
    )
    monkeypatch.setattr(
        recovery,
        "reparse_receipt",
        lambda *_args, **_kwargs: calls.append("unexpected"),
    )
    receipt_storage_root = tmp_path / "data" / "receipts" / "raw"
    receipt_storage_root.mkdir(parents=True)

    report = recovery.run_safe_stale_receipt_recovery(engine, receipt_storage_root)
    assert report["candidate_count"] == 1
    assert report["reparsed_count"] == 0
    assert report["skipped_not_improved_count"] == 1
    assert report["skipped_not_improved"][0]["receipt_table_id"] == "still-review"
    assert calls == []
