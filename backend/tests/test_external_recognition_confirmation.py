from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text

from app.services import external_database_matchflow_evidence as matchflow
from app.services import external_product_candidate_store as candidate_store
from app.services import external_recognition_confirmation as recognition


@contextmanager
def _prepared_database():
    original_candidate_engine = candidate_store.engine
    original_recognition_engine = recognition.engine

    with tempfile.TemporaryDirectory(prefix="rezzerv-recognition-") as temp_dir:
        db_path = Path(temp_dir) / "recognition-test.db"
        engine = create_engine(f"sqlite:///{db_path}", future=True)
        candidate_store.engine = engine
        recognition.engine = engine
        try:
            candidate_store.ensure_external_product_candidates_schema()
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE purchase_import_lines (
                            id TEXT PRIMARY KEY,
                            external_article_code TEXT,
                            external_source_name TEXT,
                            external_match_status TEXT,
                            updated_at TEXT
                        )
                        """
                    )
                )
                conn.execute(text("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT)"))
                conn.execute(
                    text(
                        """
                        CREATE TABLE product_identities (
                            id TEXT PRIMARY KEY,
                            identity_type TEXT,
                            identity_value TEXT,
                            global_product_id TEXT
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO purchase_import_lines (
                            id, external_article_code, external_source_name,
                            external_match_status, updated_at
                        ) VALUES ('pil-1', NULL, NULL, NULL, CURRENT_TIMESTAMP)
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
        assert int(candidate["is_user_confirmed"] or 0) == 0
        assert int(candidate["is_external_database_override"] or 0) == 0
        assert candidate["global_product_id"] is None
        assert import_line["external_article_code"] == "lidl:groente.veldsla"
        assert import_line["external_source_name"] == "lidl_catalog_enrichment"
        assert import_line["external_match_status"] == recognition.EXTERNAL_RECOGNITION_STATUS
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
