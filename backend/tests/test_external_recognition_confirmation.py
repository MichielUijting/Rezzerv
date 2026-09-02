from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db import DATASTORE_KIND, engine as app_engine
from app.services import external_database_matchflow_evidence as matchflow
from app.services import external_product_candidate_store as candidate_store
from app.services import external_recognition_confirmation as recognition


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

HOUSEHOLD_ID = "recognition-contract-household"
STORE_PROVIDER_ID = "recognition-contract-provider"
CONNECTION_ID = "recognition-contract-connection"
BATCH_ID = "recognition-contract-batch"
PURCHASE_IMPORT_LINE_ID = "recognition-contract-line"
CANDIDATE_ONE_ID = "recognition-contract-candidate-1"
CANDIDATE_TWO_ID = "recognition-contract-candidate-2"
CONTEXT_KEY = f"purchase-import-line:{PURCHASE_IMPORT_LINE_ID}"


def _canonical_head_revision() -> str:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise AssertionError(
            f"Recognition contract fixture requires one canonical Alembic head, got {heads}"
        )
    return heads[0]


def _assert_postgresql_runtime() -> None:
    if DATASTORE_KIND != "postgresql":
        raise AssertionError(
            "Recognition contract fixture requires the canonical PostgreSQL runtime"
        )


def _assert_head_revision(engine) -> None:
    expected_revision = _canonical_head_revision()
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != expected_revision:
        raise AssertionError(
            f"Recognition contract fixture expected Alembic {expected_revision}, got {revision}"
        )


def _assert_fixture_schema(conn) -> None:
    required_columns = {
        "household_store_connections": {
            "id",
            "household_id",
            "store_provider_id",
            "connection_status",
        },
        "purchase_import_batches": {
            "id",
            "household_id",
            "store_provider_id",
            "connection_id",
            "source_type",
            "import_status",
        },
        "purchase_import_lines": {
            "id",
            "batch_id",
            "external_article_code",
            "article_name_raw",
            "quantity_raw",
            "match_status",
            "updated_at",
        },
    }
    inspector = inspect(conn)
    for table_name, expected in required_columns.items():
        if not inspector.has_table(table_name):
            raise AssertionError(f"Alembic head is missing canonical {table_name}")
        actual = {
            str(column.get("name") or "")
            for column in inspector.get_columns(table_name)
        }
        missing = expected - actual
        if missing:
            raise AssertionError(
                f"Canonical {table_name} lacks recognition fixture columns: {sorted(missing)}"
            )


def _cleanup_fixture_rows(conn) -> None:
    conn.execute(
        text(
            """
            DELETE FROM external_product_candidates
            WHERE id IN (:candidate_one_id, :candidate_two_id)
            """
        ),
        {
            "candidate_one_id": CANDIDATE_ONE_ID,
            "candidate_two_id": CANDIDATE_TWO_ID,
        },
    )
    conn.execute(
        text("DELETE FROM purchase_import_lines WHERE id = :line_id"),
        {"line_id": PURCHASE_IMPORT_LINE_ID},
    )
    conn.execute(
        text("DELETE FROM purchase_import_batches WHERE id = :batch_id"),
        {"batch_id": BATCH_ID},
    )
    conn.execute(
        text("DELETE FROM household_store_connections WHERE id = :connection_id"),
        {"connection_id": CONNECTION_ID},
    )


def _insert_candidate_fixture(
    conn,
    *,
    candidate_id: str,
    candidate_name: str,
    source_product_code: str,
    score: float,
    status: str,
    is_probable: bool,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO external_product_candidates (
                id, purchase_import_line_id, context_key, retailer_code,
                receipt_line_text, candidate_name, candidate_brand,
                candidate_source_name, candidate_source_product_code,
                source_name, source_product_code, retailer_article_number,
                score, status, candidate_status, is_probable,
                is_user_confirmed, is_external_database_override,
                created_at, updated_at, global_product_id
            ) VALUES (
                :candidate_id, :purchase_import_line_id, :context_key, 'lidl',
                'Veldsla', :candidate_name, 'Lidl',
                'lidl_catalog_enrichment', :source_product_code,
                'lidl_catalog_enrichment', :source_product_code, :source_product_code,
                :score, :status, :status, :is_probable,
                FALSE, FALSE,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
            )
            """
        ),
        {
            "candidate_id": candidate_id,
            "purchase_import_line_id": PURCHASE_IMPORT_LINE_ID,
            "context_key": CONTEXT_KEY,
            "candidate_name": candidate_name,
            "source_product_code": source_product_code,
            "score": score,
            "status": status,
            "is_probable": is_probable,
        },
    )


def _insert_fixture_rows(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_store_connections (
                id, household_id, store_provider_id, connection_status
            ) VALUES (
                :connection_id, :household_id, :store_provider_id, 'active'
            )
            """
        ),
        {
            "connection_id": CONNECTION_ID,
            "household_id": HOUSEHOLD_ID,
            "store_provider_id": STORE_PROVIDER_ID,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_batches (
                id, household_id, store_provider_id, connection_id,
                source_type, import_status
            ) VALUES (
                :batch_id, :household_id, :store_provider_id, :connection_id,
                'recognition_contract', 'new'
            )
            """
        ),
        {
            "batch_id": BATCH_ID,
            "household_id": HOUSEHOLD_ID,
            "store_provider_id": STORE_PROVIDER_ID,
            "connection_id": CONNECTION_ID,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO purchase_import_lines (
                id, batch_id, external_article_code,
                article_name_raw, quantity_raw, match_status
            ) VALUES (
                :line_id, :batch_id, NULL,
                'Veldsla', 1.00, 'unmatched'
            )
            """
        ),
        {"line_id": PURCHASE_IMPORT_LINE_ID, "batch_id": BATCH_ID},
    )
    _insert_candidate_fixture(
        conn,
        candidate_id=CANDIDATE_ONE_ID,
        candidate_name="Lidl Veldsla",
        source_product_code="lidl:groente.veldsla",
        score=0.95,
        status="probable_candidate",
        is_probable=True,
    )
    _insert_candidate_fixture(
        conn,
        candidate_id=CANDIDATE_TWO_ID,
        candidate_name="Alternatieve Veldsla",
        source_product_code="lidl:groente.veldsla-alt",
        score=0.90,
        status="possible_candidate",
        is_probable=False,
    )


def _catalog_counts(conn) -> tuple[int, int]:
    global_product_count = int(
        conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
    )
    product_identity_count = int(
        conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one()
    )
    return global_product_count, product_identity_count


@contextmanager
def _prepared_database():
    _assert_postgresql_runtime()
    original_candidate_engine = candidate_store.engine
    original_recognition_engine = recognition.engine
    candidate_store.engine = app_engine
    recognition.engine = app_engine

    try:
        _assert_head_revision(app_engine)
        candidate_store.ensure_external_product_candidates_schema()
        with app_engine.begin() as conn:
            _assert_fixture_schema(conn)
            _cleanup_fixture_rows(conn)
            _insert_fixture_rows(conn)
        yield app_engine
    finally:
        try:
            with app_engine.begin() as conn:
                _cleanup_fixture_rows(conn)
        finally:
            candidate_store.engine = original_candidate_engine
            recognition.engine = original_recognition_engine


def test_confirm_recognition_does_not_create_catalog_or_inventory_data():
    with _prepared_database() as engine:
        with engine.connect() as conn:
            baseline_global_product_count, baseline_product_identity_count = _catalog_counts(conn)

        result = recognition.confirm_external_recognition(CANDIDATE_ONE_ID)

        assert result["ok"] is True
        assert result["confirmed"] is True
        assert result["external_product_code"] == "lidl:groente.veldsla"
        assert result["external_source_name"] == "lidl_catalog_enrichment"
        assert result["purchase_import_line_updated_count"] == 1
        assert result["creates_global_product"] is False
        assert result["creates_product_identity"] is False
        assert result["creates_household_article"] is False
        assert result["creates_inventory_event"] is False

        with engine.begin() as conn:
            candidate = conn.execute(
                text("SELECT * FROM external_product_candidates WHERE id = :candidate_id"),
                {"candidate_id": CANDIDATE_ONE_ID},
            ).mappings().one()
            import_line = conn.execute(
                text("SELECT * FROM purchase_import_lines WHERE id = :line_id"),
                {"line_id": PURCHASE_IMPORT_LINE_ID},
            ).mappings().one()
            global_product_count, product_identity_count = _catalog_counts(conn)

        assert candidate["status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert candidate["candidate_status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert candidate["candidate_source_name"] == "lidl_catalog_enrichment"
        assert int(candidate["is_user_confirmed"] or 0) == 0
        assert int(candidate["is_external_database_override"] or 0) == 0
        assert candidate["global_product_id"] is None
        assert import_line["external_article_code"] == "lidl:groente.veldsla"
        assert global_product_count == baseline_global_product_count
        assert product_identity_count == baseline_product_identity_count

        state = recognition.get_external_recognition_state({
            "purchase_import_line_id": PURCHASE_IMPORT_LINE_ID,
            "context_key": CONTEXT_KEY,
            "receipt_line_text": "Veldsla",
            "retailer_code": "lidl",
        })
        assert state["resolved"] is True
        assert state["candidate_id"] == CANDIDATE_ONE_ID
        assert state["external_product_code"] == "lidl:groente.veldsla"
        assert state["external_source_name"] == "lidl_catalog_enrichment"


def test_recognition_confirmation_is_idempotent_and_requires_explicit_overwrite():
    with _prepared_database() as engine:
        first = recognition.confirm_external_recognition(CANDIDATE_ONE_ID)
        second = recognition.confirm_external_recognition(CANDIDATE_ONE_ID)
        blocked_switch = recognition.confirm_external_recognition(CANDIDATE_TWO_ID)

        assert first["confirmed"] is True
        assert second["confirmed"] is True
        assert second["already_confirmed"] is True
        assert blocked_switch["confirmed"] is False
        assert blocked_switch["requires_overwrite"] is True

        switched = recognition.confirm_external_recognition(
            CANDIDATE_TWO_ID,
            force_overwrite=True,
        )
        assert switched["confirmed"] is True

        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, status, candidate_status, global_product_id,
                           is_user_confirmed, is_external_database_override
                    FROM external_product_candidates
                    WHERE id IN (:candidate_one_id, :candidate_two_id)
                    ORDER BY id
                    """
                ),
                {
                    "candidate_one_id": CANDIDATE_ONE_ID,
                    "candidate_two_id": CANDIDATE_TWO_ID,
                },
            ).mappings().all()

        by_id = {row["id"]: row for row in rows}
        assert by_id[CANDIDATE_ONE_ID]["status"] != recognition.EXTERNAL_RECOGNITION_STATUS
        assert (
            by_id[CANDIDATE_ONE_ID]["candidate_status"]
            != recognition.EXTERNAL_RECOGNITION_STATUS
        )
        assert by_id[CANDIDATE_TWO_ID]["status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert (
            by_id[CANDIDATE_TWO_ID]["candidate_status"]
            == recognition.EXTERNAL_RECOGNITION_STATUS
        )
        assert by_id[CANDIDATE_TWO_ID]["global_product_id"] is None
        assert int(by_id[CANDIDATE_TWO_ID]["is_user_confirmed"] or 0) == 0
        assert int(by_id[CANDIDATE_TWO_ID]["is_external_database_override"] or 0) == 0


def test_confirmed_recognition_is_skipped_by_later_candidate_search():
    with _prepared_database():
        recognition.confirm_external_recognition(CANDIDATE_ONE_ID)
        original_ensure = matchflow.candidate_store.ensure_external_receipt_item_candidates
        captured = {}

        def fake_ensure_external_receipt_item_candidates(*args, **kwargs):
            items = kwargs.get("items") if "items" in kwargs else (args[0] if args else [])
            captured["items"] = list(items or [])
            return {
                "ok": True,
                "processed": len(items or []),
                "saved_count": 0,
                "updated_count": 0,
                "skipped_count": 0,
                "errors": [],
            }

        matchflow.candidate_store.ensure_external_receipt_item_candidates = (
            fake_ensure_external_receipt_item_candidates
        )
        try:
            resolved_item = {
                "purchase_import_line_id": PURCHASE_IMPORT_LINE_ID,
                "context_key": CONTEXT_KEY,
                "receipt_line_text": "Veldsla",
                "retailer_code": "lidl",
            }
            unresolved_item = {
                "purchase_import_line_id": "recognition-contract-unresolved-line",
                "context_key": "purchase-import-line:recognition-contract-unresolved-line",
                "receipt_line_text": "Nieuw onbekend artikel",
                "retailer_code": "lidl",
            }

            result = matchflow.ensure_external_receipt_item_candidates(
                items=[resolved_item, unresolved_item],
                include_below_threshold=True,
            )
        finally:
            matchflow.candidate_store.ensure_external_receipt_item_candidates = original_ensure

        assert captured["items"] == [unresolved_item]
        assert result["external_resolved_excluded_count"] == 1
        assert result["external_matching_excluded_count"] == 1
        assert result["creates_global_product"] is False
        assert result["creates_household_article"] is False
        assert result["creates_inventory_event"] is False


def run() -> None:
    test_confirm_recognition_does_not_create_catalog_or_inventory_data()
    test_recognition_confirmation_is_idempotent_and_requires_explicit_overwrite()
    test_confirmed_recognition_is_skipped_by_later_candidate_search()
    print("EXTERNAL_RECOGNITION_CONFIRMATION_CONTRACT_GREEN")


if __name__ == "__main__":
    run()
