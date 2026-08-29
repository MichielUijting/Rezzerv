from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.services import external_database_matchflow_evidence as matchflow
from app.services import external_product_candidate_store as candidate_store
from app.services import external_recognition_confirmation as recognition


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
HEAD_REVISION = "20260829_07"


def _database_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _migrate_database(path: Path) -> None:
    database_url = _database_url(path)
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["MIGRATION_DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Recognition contract fixture could not migrate through Alembic head:\n"
            + result.stdout
            + result.stderr
        )


def _fixture_value(column_name: str, declared_type: str) -> Any:
    if column_name == "id":
        return "pil-1"
    if column_name == "purchase_import_id":
        return "purchase-import-recognition-contract"
    if column_name == "receipt_line_index":
        return 1
    if column_name in {"raw_text", "normalized_text"}:
        return "Veldsla"
    if column_name == "quantity":
        return 1
    if column_name == "unit":
        return "stuk"
    if column_name == "line_total":
        return 1.0
    if column_name == "linked_status":
        return "unlinked"
    if column_name.endswith("_at"):
        return "2026-08-29 12:00:00"

    normalized_type = str(declared_type or "").upper()
    if "INT" in normalized_type or "BOOL" in normalized_type:
        return 0
    if any(token in normalized_type for token in ("REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL")):
        return 0.0
    return f"recognition-contract-{column_name}"


def _insert_purchase_import_line_fixture(conn) -> None:
    rows = conn.exec_driver_sql("PRAGMA table_info(purchase_import_lines)").mappings().all()
    if not rows:
        raise AssertionError("Alembic head is missing canonical purchase_import_lines")

    columns = {str(row.get("name") or ""): row for row in rows}
    required_contract = {
        "id",
        "external_article_code",
        "updated_at",
    }
    missing = required_contract - set(columns)
    if missing:
        raise AssertionError(
            f"Canonical purchase_import_lines lacks recognition projection columns: {sorted(missing)}"
        )

    values: dict[str, Any] = {
        "id": "pil-1",
        "external_article_code": None,
    }
    for column_name, row in columns.items():
        if column_name in values:
            continue
        is_required = bool(row.get("notnull")) and row.get("dflt_value") is None
        if is_required:
            values[column_name] = _fixture_value(column_name, str(row.get("type") or ""))

    names = list(values)
    quoted_names = ", ".join(f'"{name}"' for name in names)
    parameters = ", ".join(f":{name}" for name in names)
    conn.execute(
        text(f"INSERT INTO purchase_import_lines ({quoted_names}) VALUES ({parameters})"),
        values,
    )


def _assert_head_revision(engine) -> None:
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != HEAD_REVISION:
        raise AssertionError(
            f"Recognition contract fixture expected Alembic {HEAD_REVISION}, got {revision}"
        )


@contextmanager
def _prepared_database():
    original_candidate_engine = candidate_store.engine
    original_recognition_engine = recognition.engine

    with tempfile.TemporaryDirectory(prefix="rezzerv-recognition-") as temp_dir:
        db_path = Path(temp_dir) / "recognition-test.db"
        _migrate_database(db_path)
        engine = create_engine(_database_url(db_path), future=True)
        candidate_store.engine = engine
        recognition.engine = engine
        try:
            _assert_head_revision(engine)
            # Runtime schema helpers are validation-only under PR2h. The fixture must
            # therefore be migration-first and this call may only validate Alembic's schema.
            candidate_store.ensure_external_product_candidates_schema()
            with engine.begin() as conn:
                _insert_purchase_import_line_fixture(conn)
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
                            'candidate-1', 'pil-1', 'purchase-import-line:pil-1', 'lidl',
                            'Veldsla', 'Lidl Veldsla', 'Lidl',
                            'lidl_catalog_enrichment', 'lidl:groente.veldsla',
                            'lidl_catalog_enrichment', 'lidl:groente.veldsla',
                            'lidl:groente.veldsla', 0.95, 'probable_candidate',
                            'probable_candidate', 1, 0, 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
                        )
                        """
                    )
                )
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
                            'candidate-2', 'pil-1', 'purchase-import-line:pil-1', 'lidl',
                            'Veldsla', 'Alternatieve Veldsla', 'Lidl',
                            'lidl_catalog_enrichment', 'lidl:groente.veldsla-alt',
                            'lidl_catalog_enrichment', 'lidl:groente.veldsla-alt',
                            'lidl:groente.veldsla-alt', 0.90, 'possible_candidate',
                            'possible_candidate', 0, 0, 0,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL
                        )
                        """
                    )
                )

            yield engine
        finally:
            candidate_store.engine = original_candidate_engine
            recognition.engine = original_recognition_engine
            engine.dispose()


def test_confirm_recognition_does_not_create_catalog_or_inventory_data():
    with _prepared_database() as engine:
        result = recognition.confirm_external_recognition("candidate-1")

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
                text("SELECT * FROM external_product_candidates WHERE id = 'candidate-1'")
            ).mappings().one()
            import_line = conn.execute(
                text("SELECT * FROM purchase_import_lines WHERE id = 'pil-1'")
            ).mappings().one()
            global_product_count = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
            product_identity_count = conn.execute(text("SELECT COUNT(*) FROM product_identities")).scalar_one()

        assert candidate["status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert candidate["candidate_status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert candidate["candidate_source_name"] == "lidl_catalog_enrichment"
        assert int(candidate["is_user_confirmed"] or 0) == 0
        assert int(candidate["is_external_database_override"] or 0) == 0
        assert candidate["global_product_id"] is None
        assert import_line["external_article_code"] == "lidl:groente.veldsla"
        assert global_product_count == 0
        assert product_identity_count == 0

        state = recognition.get_external_recognition_state({
            "purchase_import_line_id": "pil-1",
            "context_key": "purchase-import-line:pil-1",
            "receipt_line_text": "Veldsla",
            "retailer_code": "lidl",
        })
        assert state["resolved"] is True
        assert state["candidate_id"] == "candidate-1"
        assert state["external_product_code"] == "lidl:groente.veldsla"
        assert state["external_source_name"] == "lidl_catalog_enrichment"


def test_recognition_confirmation_is_idempotent_and_requires_explicit_overwrite():
    with _prepared_database() as engine:
        first = recognition.confirm_external_recognition("candidate-1")
        second = recognition.confirm_external_recognition("candidate-1")
        blocked_switch = recognition.confirm_external_recognition("candidate-2")

        assert first["confirmed"] is True
        assert second["confirmed"] is True
        assert second["already_confirmed"] is True
        assert blocked_switch["confirmed"] is False
        assert blocked_switch["requires_overwrite"] is True

        switched = recognition.confirm_external_recognition("candidate-2", force_overwrite=True)
        assert switched["confirmed"] is True

        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, status, candidate_status, global_product_id,
                           is_user_confirmed, is_external_database_override
                    FROM external_product_candidates
                    ORDER BY id
                    """
                )
            ).mappings().all()

        by_id = {row["id"]: row for row in rows}
        assert by_id["candidate-1"]["status"] != recognition.EXTERNAL_RECOGNITION_STATUS
        assert by_id["candidate-1"]["candidate_status"] != recognition.EXTERNAL_RECOGNITION_STATUS
        assert by_id["candidate-2"]["status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert by_id["candidate-2"]["candidate_status"] == recognition.EXTERNAL_RECOGNITION_STATUS
        assert by_id["candidate-2"]["global_product_id"] is None
        assert int(by_id["candidate-2"]["is_user_confirmed"] or 0) == 0
        assert int(by_id["candidate-2"]["is_external_database_override"] or 0) == 0


def test_confirmed_recognition_is_skipped_by_later_candidate_search():
    with _prepared_database():
        recognition.confirm_external_recognition("candidate-1")
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

        matchflow.candidate_store.ensure_external_receipt_item_candidates = fake_ensure_external_receipt_item_candidates
        try:
            resolved_item = {
                "purchase_import_line_id": "pil-1",
                "context_key": "purchase-import-line:pil-1",
                "receipt_line_text": "Veldsla",
                "retailer_code": "lidl",
            }
            unresolved_item = {
                "purchase_import_line_id": "pil-2",
                "context_key": "purchase-import-line:pil-2",
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
