from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.system_routes import router as system_router
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


def _exercise_ed2_articles_overview_http_path() -> None:
    app = FastAPI()
    app.include_router(system_router)
    client = TestClient(app)
    # Legacy /receipt-items is deliberately retired. Exercise the retained ED2
    # read path against the DML-only PostgreSQL runtime role instead.
    response = client.get("/api/external-databases/articles-overview")
    if response.status_code != 200:
        raise AssertionError(
            "ED2 articles-overview PostgreSQL request failed: "
            f"status={response.status_code} body={response.text}"
        )
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise AssertionError(f"ED2 articles-overview response shape is invalid: {payload!r}")
    if not isinstance(payload.get("counts"), dict) or not {
        "unlinked", "classification_pending", "linked"
    }.issubset(payload["counts"]):
        raise AssertionError(f"ED2 classification counters missing: {payload!r}")
    print("POSTGRESQL_ED2_ARTICLES_OVERVIEW_REQUEST_GREEN")
    _exercise_weight_detail_repair_and_source_filter()


def _exercise_weight_detail_repair_and_source_filter() -> None:
    from app.maintenance.repair_weight_detail_rows import build_plan, apply_plan, plan_digest
    from app.maintenance import repair_legacy_deposit_rows as deposits
    from app.services.external_unlinked_articles_service import _source_articles

    prefix = f"__weight_{uuid.uuid4()}"
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            for suffix in ('live', 'removed'):
                receipt = prefix + suffix
                conn.execute(text('''INSERT INTO raw_receipts
                    (id, household_id, original_filename, mime_type, storage_path, sha256_hash, raw_status)
                    VALUES (:id, '0', 'weight-test', 'application/json', 'test-only', :hash, 'stored')'''),
                    {'id': receipt, 'hash': uuid.uuid4().hex * 2})
                conn.execute(text('''INSERT INTO receipt_tables
                    (id, raw_receipt_id, household_id, workflow_state, store_name, currency, parse_status, line_count)
                    VALUES (:id, :id, '0', 'active', 'Lidl', 'EUR', 'review_needed', 6)'''), {'id': receipt})
                for index, role, deleted, raw in (
                    (0, 'product', False, 'GEMBER'),
                    (1, 'product', False, '0,094 kg x 5,99 EUR'),
                    (2, 'loyalty', False, 'Koopzegel'),
                    (3, 'product', True, 'Verwijderd'),
                    (4, 'financial', False, 'Statiegeld'),
                    (5, 'product', False, 'Statiegeld')):
                    conn.execute(text('''INSERT INTO receipt_table_lines
                        (id, receipt_table_id, line_index, raw_label, normalized_label, quantity,
                         unit_price, line_total, external_article_code, article_match_status,
                         line_role, inventory_eligible, is_deleted)
                        VALUES (:id, :receipt, :idx, :raw, :normalized, .094, 5.99, .56,
                                'WEIGHT-TEST', 'unmatched', :role, :eligible, :deleted)'''),
                        {'id': receipt + str(index), 'receipt': receipt, 'idx': index,
                         'raw': raw, 'normalized': 'Gember' if index < 2 else raw,
                         'role': role, 'eligible': int(role == 'product'), 'deleted': deleted})
                if suffix == 'removed':
                    conn.execute(text('UPDATE raw_receipts SET deleted_at=CURRENT_TIMESTAMP WHERE id=:id'), {'id': receipt})
            conn.execute(text('''INSERT INTO store_providers (id, code, name, status, import_mode)
                VALUES (:id, :id, 'Test', 'active', 'receipt')'''), {'id': prefix})
            conn.execute(text('''INSERT INTO household_store_connections
                (id, household_id, store_provider_id, connection_status)
                VALUES (:id, '0', :id, 'active')'''), {'id': prefix})
            for source_type in ('receipt', 'mock'):
                conn.execute(text('''INSERT INTO purchase_import_batches
                    (id, household_id, store_provider_id, connection_id, source_type, import_status)
                    VALUES (:batch, '0', :id, :id, :source_type, 'new')'''),
                    {'batch': prefix + source_type, 'id': prefix, 'source_type': source_type})
            for suffix, source_type, reference, label in (
                ('deposit-copy', 'receipt', 'receipt-line:' + prefix + 'live4', 'Statiegeld'),
                ('orphan-copy', 'receipt', None, 'Verouderde bonkopie'),
                ('mislabelled-copy', 'mock', 'receipt-line:' + prefix + 'removed0', 'Verwijderde bonkopie'),
                ('real-purchase', 'mock', 'independent-product', 'Melk'),
                ('legacy-import-deposit', 'mock', 'independent-deposit', 'Statiegeld')):
                conn.execute(text('''INSERT INTO purchase_import_lines
                    (id, batch_id, external_line_ref, article_name_raw, quantity_raw, line_price_raw, match_status)
                    VALUES (:id, :batch, :reference, :label, 1, .15, 'unmatched')'''),
                    {'id': prefix + suffix, 'batch': prefix + source_type, 'reference': reference, 'label': label})
            purchase_plan = deposits.build_purchase_plan(conn)
            assert prefix + 'legacy-import-deposit' in {row['id'] for row in purchase_plan}
            deposits.apply_purchase_plan(conn, plan_digest(purchase_plan))
            assert not any(row['id'].startswith(prefix) for row in deposits.build_purchase_plan(conn))
            purchases = [row for row in _source_articles(conn)
                         if str(row.get('purchase_import_line_id', '')).startswith(prefix)]
            assert [row['purchase_import_line_id'] for row in purchases] == [prefix + 'real-purchase'], purchases
            sources = [row for row in _source_articles(conn) if str(row.get('receipt_line_id', '')).startswith(prefix)]
            assert len(sources) == 3, sources
            deposit_plan = deposits.build_plan(conn)
            assert {prefix + suffix + '5' for suffix in ('live', 'removed')} <= {row['id'] for row in deposit_plan}
            deposits.apply_plan(conn, plan_digest(deposit_plan))
            assert not any(row['id'].startswith(prefix) for row in deposits.build_plan(conn))
            repaired_deposit = conn.execute(text('''SELECT line_role, inventory_eligible, is_deleted, line_total
                FROM receipt_table_lines WHERE id=:id'''), {'id': prefix + 'live5'}).one()
            assert repaired_deposit[:3] == ('financial', 0, False), repaired_deposit
            assert str(repaired_deposit[3]) == '0.56', repaired_deposit
            sources = [row for row in _source_articles(conn) if str(row.get('receipt_line_id', '')).startswith(prefix)]
            assert len(sources) == 2, sources
            assert all(row['receipt_line_text'] == 'Gember' for row in sources)
            plan = build_plan(conn)
            assert {prefix + suffix + '1' for suffix in ('live', 'removed')} <= {row['id'] for row in plan}
            apply_plan(conn, plan_digest(plan))
            assert not any(row['id'].startswith(prefix) for row in build_plan(conn))
            sources = [row for row in _source_articles(conn) if str(row.get('receipt_line_id', '')).startswith(prefix)]
            assert len(sources) == 1 and sources[0]['receipt_line_id'] == prefix + 'live0', sources
            original = conn.execute(text('SELECT is_deleted, line_role FROM receipt_table_lines WHERE id=:id'), {'id': prefix + 'live0'}).one()
            assert original == (False, 'product'), original
        finally:
            transaction.rollback()
    print('POSTGRESQL_WEIGHT_DETAIL_REPAIR_AND_SOURCE_FILTER_GREEN')


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
    _exercise_ed2_articles_overview_http_path()
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
