from __future__ import annotations

import sys
import uuid
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine
from app.services.external_article_product_link_service import (
    get_confirmed_external_article_product_link,
)
from app.services.external_product_candidate_store import (
    ensure_external_product_candidates_schema,
    list_saved_external_product_candidates,
)
from app.services.external_product_index_store import (
    ensure_external_product_index_schema,
    ensure_external_product_index_seeded,
    search_external_product_index_candidates,
)
from app.services.external_recognition_confirmation import (
    confirm_external_recognition,
    get_external_recognition_state,
)
from app.services.external_relation_batch_store import (
    apply_external_relation_batch_decision,
    ensure_external_relation_batch_schema,
)

CANDIDATE_ID = f"__pr2h_candidate_{uuid.uuid4()}__"
CONTEXT_KEY = f"__pr2h_context_{uuid.uuid4()}__"
EXTERNAL_CODE = "PR2H-EXT-001"


def _assert_runtime_has_no_schema_create() -> None:
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise AssertionError(
                f"PR2h DML-only proof requires PostgreSQL, got {conn.dialect.name}"
            )
        has_create = bool(
            conn.execute(
                text(
                    "SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')"
                )
            ).scalar_one()
        )
        if has_create:
            raise AssertionError("Runtime role unexpectedly has schema CREATE privilege")
    print("POSTGRESQL_EXTERNAL_CATALOG_RUNTIME_CREATE_DENIED_GREEN")


def _validate_alembic_owned_schema() -> None:
    ensure_external_product_candidates_schema()
    ensure_external_product_index_schema()
    ensure_external_relation_batch_schema()
    seeded = ensure_external_product_index_seeded(minimum_rows=1)
    if int(seeded.get("rows") or 0) < 1:
        raise AssertionError(f"External product index bootstrap is missing: {seeded}")
    print("POSTGRESQL_EXTERNAL_CATALOG_SCHEMA_VALIDATION_ONLY_GREEN")


def _exercise_external_index_read_path() -> None:
    rows = search_external_product_index_candidates(
        "melk",
        retailer_code="lidl",
        limit=25,
    )
    if not isinstance(rows, list):
        raise AssertionError(f"External index search returned invalid result: {rows!r}")
    print("POSTGRESQL_EXTERNAL_INDEX_REQUEST_READ_GREEN")


def _insert_candidate_fixture() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM external_relation_batch_decisions WHERE candidate_id = :candidate_id"),
            {"candidate_id": CANDIDATE_ID},
        )
        conn.execute(
            text("DELETE FROM external_product_candidates WHERE id = :candidate_id"),
            {"candidate_id": CANDIDATE_ID},
        )
        conn.execute(
            text(
                """
                INSERT INTO external_product_candidates (
                    id,
                    purchase_import_line_id,
                    context_key,
                    retailer_code,
                    receipt_line_text,
                    candidate_name,
                    candidate_source_name,
                    candidate_source_product_code,
                    source_name,
                    source_product_code,
                    retailer_article_number,
                    external_article_code,
                    score,
                    status,
                    candidate_status,
                    is_probable,
                    is_user_confirmed,
                    is_external_database_override,
                    created_by,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :purchase_import_line_id,
                    :context_key,
                    :retailer_code,
                    :receipt_line_text,
                    :candidate_name,
                    :candidate_source_name,
                    :candidate_source_product_code,
                    :source_name,
                    :source_product_code,
                    :retailer_article_number,
                    :external_article_code,
                    :score,
                    :status,
                    :candidate_status,
                    :is_probable,
                    :is_user_confirmed,
                    :is_external_database_override,
                    :created_by,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": CANDIDATE_ID,
                "purchase_import_line_id": f"preview:{CONTEXT_KEY}",
                "context_key": CONTEXT_KEY,
                "retailer_code": "lidl",
                "receipt_line_text": "PR2h portable candidate",
                "candidate_name": "PR2h Portable Candidate",
                "candidate_source_name": "pr2h_runtime_test",
                "candidate_source_product_code": EXTERNAL_CODE,
                "source_name": "pr2h_runtime_test",
                "source_product_code": EXTERNAL_CODE,
                "retailer_article_number": EXTERNAL_CODE,
                "external_article_code": EXTERNAL_CODE,
                "score": 0.99,
                "status": "candidate",
                "candidate_status": "candidate",
                "is_probable": True,
                "is_user_confirmed": False,
                "is_external_database_override": False,
                "created_by": "postgresql_external_catalog_dml_only_selftest",
            },
        )


def _exercise_candidate_and_recognition_paths() -> None:
    _insert_candidate_fixture()

    saved = list_saved_external_product_candidates(context_key=CONTEXT_KEY, limit=10)
    items = list(saved.get("items") or [])
    if len(items) != 1 or str(items[0].get("id") or "") != CANDIDATE_ID:
        raise AssertionError(f"Candidate request read path failed: {saved}")

    before = get_external_recognition_state({"context_key": CONTEXT_KEY})
    if bool(before.get("resolved")):
        raise AssertionError(f"Fresh candidate unexpectedly resolved: {before}")

    confirmed = confirm_external_recognition(CANDIDATE_ID)
    if not bool(confirmed.get("confirmed")):
        raise AssertionError(f"Recognition confirmation DML failed: {confirmed}")

    after = get_external_recognition_state({"context_key": CONTEXT_KEY})
    if not bool(after.get("resolved")):
        raise AssertionError(f"Recognition request read did not observe confirmation: {after}")

    print("POSTGRESQL_EXTERNAL_CANDIDATE_RECOGNITION_DML_ONLY_GREEN")


def _exercise_relation_batch_path() -> None:
    result = apply_external_relation_batch_decision(
        candidate_id=CANDIDATE_ID,
        decision="later",
        decision_reason="PR2h DML-only runtime proof",
        created_by="postgresql_external_catalog_dml_only_selftest",
    )
    if not bool(result.get("ok")) or result.get("decision") != "later":
        raise AssertionError(f"Relation-batch request DML failed: {result}")

    with engine.connect() as conn:
        stored = conn.execute(
            text(
                """
                SELECT decision
                FROM external_relation_batch_decisions
                WHERE candidate_id = :candidate_id
                  AND decision = 'later'
                LIMIT 1
                """
            ),
            {"candidate_id": CANDIDATE_ID},
        ).scalar_one_or_none()
    if stored != "later":
        raise AssertionError(f"Relation-batch decision was not persisted: {stored!r}")
    print("POSTGRESQL_EXTERNAL_RELATION_BATCH_DML_ONLY_GREEN")


def _exercise_external_link_read_path() -> None:
    with engine.connect() as conn:
        link = get_confirmed_external_article_product_link(
            conn,
            retailer_code="pr2h-runtime-test",
            external_article_code="does-not-exist",
        )
    if link is not None:
        raise AssertionError(f"Synthetic nonexistent external link unexpectedly resolved: {link}")
    print("POSTGRESQL_EXTERNAL_LINK_REQUEST_READ_GREEN")


def _cleanup() -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM external_relation_batch_decisions WHERE candidate_id = :candidate_id"),
            {"candidate_id": CANDIDATE_ID},
        )
        conn.execute(
            text("DELETE FROM external_product_candidates WHERE id = :candidate_id"),
            {"candidate_id": CANDIDATE_ID},
        )


def main() -> None:
    _assert_runtime_has_no_schema_create()
    _validate_alembic_owned_schema()
    _exercise_external_index_read_path()
    try:
        _exercise_candidate_and_recognition_paths()
        _exercise_relation_batch_path()
        _exercise_external_link_read_path()
    finally:
        _cleanup()
    print("POSTGRESQL_EXTERNAL_CATALOG_DML_ONLY_GREEN")
    print("POSTGRESQL_EXTERNAL_CATALOG_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
