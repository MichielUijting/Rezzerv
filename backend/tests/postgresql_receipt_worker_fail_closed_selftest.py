from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from app.db import engine
import app.main as main


EXPECTED_ERROR = "F5 deliberate receipt member failure"


def main_test() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name

    household_id = f"f5-worker-{uuid.uuid4()}"
    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
        )
        assert current_user == "rezzerv_app", current_user
        assert runtime_create is False, runtime_create
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": household_id, "naam": "F5 receipt worker fail-closed"},
        )

    created = main.create_receipt_import_batch(
        household_id=household_id,
        source_filename="f5-worker-fail-closed.zip",
        total_files=1,
    )
    batch_id = str(created.get("batch_id") or created.get("id") or "").strip()
    assert batch_id, created

    original_import = main.import_uploaded_receipt_payload

    def fail_receipt_import(**_: object) -> dict[str, object]:
        raise RuntimeError(EXPECTED_ERROR)

    main.import_uploaded_receipt_payload = fail_receipt_import
    try:
        main._run_receipt_zip_import_batch(
            batch_id=batch_id,
            household_id=household_id,
            source_id="f5-worker-source",
            source_filename="f5-worker-fail-closed.zip",
            members=[
                {
                    "filename": "broken-receipt.pdf",
                    "archive_path": "broken-receipt.pdf",
                    "bytes": b"not-a-real-receipt",
                    "mime_type": "application/pdf",
                }
            ],
        )
    finally:
        main.import_uploaded_receipt_payload = original_import

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, household_id, status, total_files, processed_files,
                       imported_files, duplicate_files, failed_files,
                       results_json, finished_at
                FROM receipt_import_batches
                WHERE id = :id
                """
            ),
            {"id": batch_id},
        ).mappings().one()

    assert str(row["household_id"]) == household_id, row
    assert str(row["status"]) == "completed_with_errors", row
    assert str(row["status"]) != "running", row
    assert str(row["status"]) != "completed", row
    assert int(row["total_files"] or 0) == 1, row
    assert int(row["processed_files"] or 0) == 1, row
    assert int(row["imported_files"] or 0) == 0, row
    assert int(row["duplicate_files"] or 0) == 0, row
    assert int(row["failed_files"] or 0) == 1, row
    assert row["finished_at"] is not None, row

    results = json.loads(str(row["results_json"] or "[]"))
    assert isinstance(results, list) and len(results) == 1, results
    failed_result = results[0]
    assert failed_result.get("filename") == "broken-receipt.pdf", failed_result
    assert failed_result.get("archive_path") == "broken-receipt.pdf", failed_result
    assert failed_result.get("import_status") == "failed", failed_result
    assert EXPECTED_ERROR in str(failed_result.get("error_message") or ""), failed_result

    print(f"batch_id={batch_id}")
    print("PASS receipt_worker_failure_not_left_running")
    print("PASS receipt_worker_failure_not_mislabeled_completed")
    print("PASS receipt_worker_failure_count_persisted")
    print("PASS receipt_worker_failure_detail_persisted")
    print("PASS receipt_worker_finished_at_persisted")
    print("PASS postgresql_runtime_is_dml_only")
    print("F5_RECEIPT_WORKER_FAIL_CLOSED_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
