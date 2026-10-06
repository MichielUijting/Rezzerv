from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.services.receipt_duplicate_guard import (
    StructuredReceiptDuplicateCandidate,
    build_candidate_fingerprint,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_service.py"
GUARD_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_duplicate_guard.py"


def _service_source() -> str:
    return SERVICE_PATH.read_text(encoding="utf-8")


def _guard_source() -> str:
    return GUARD_PATH.read_text(encoding="utf-8")


def test_duplicate_authority_is_separate_from_scanner_and_parser() -> None:
    source = _guard_source()

    assert "receipt_scanners" not in source
    assert "scan_receipt_content_via_gateway" not in source
    assert "ReceiptParseResult" not in source
    assert "class StructuredReceiptDuplicateCandidate" in source
    assert "def evaluate_structured_receipt_duplicate(" in source


def test_global_receipt_dedupe_blocks_all_non_removed_lifecycle_states() -> None:
    source = _guard_source()

    assert "_REIMPORT_ALLOWED_WORKFLOW_STATES = {'removed_reimport_allowed', 'legacy_deleted'}" in source
    assert "def _blocks_receipt_reimport(workflow_state: str | None) -> bool:" in source
    assert "return normalized not in _REIMPORT_ALLOWED_WORKFLOW_STATES" in source


def test_exact_content_hash_dedupe_is_household_scoped_and_lifecycle_aware() -> None:
    source = _guard_source()
    start = source.index("def find_existing_receipt_by_content_hash(")
    end = source.index("def find_existing_receipt_by_fingerprint(", start)
    block = source[start:end]

    assert "rr.household_id = :household_id" in block
    assert "rr.sha256_hash = :sha256_hash" in block
    assert "removed_reimport_allowed" in block
    assert "legacy_deleted" in block
    assert "rr.updated_at" not in block


def test_cross_source_fingerprint_dedupe_keeps_archived_and_processed_history() -> None:
    source = _guard_source()
    start = source.index("def find_existing_receipt_by_fingerprint(")
    end = source.index("def evaluate_structured_receipt_duplicate(", start)
    block = source[start:end]

    assert "rt.household_id = :household_id" in block
    assert "removed_reimport_allowed" in block
    assert "legacy_deleted" in block
    assert "rt.deleted_at IS NULL" not in block
    assert "_fingerprint_from_stored_receipt(" in block


def test_candidate_fingerprint_needs_no_scanner_contract() -> None:
    candidate = StructuredReceiptDuplicateCandidate(
        source_sha256="a" * 64,
        store_name="Albert Heijn",
        purchase_at="2026-10-06T12:30:00",
        total_amount=Decimal("12.34"),
        lines=(
            {"normalized_label": "Melk", "line_total": 2.49},
            {"normalized_label": "Brood", "line_total": 3.15},
        ),
    )

    fingerprint = build_candidate_fingerprint(candidate)

    assert "albert heijn" in fingerprint
    assert "2026-10-06 12:30" in fingerprint
    assert "12.34" in fingerprint
    assert "melk|2.49" in fingerprint


def test_ingest_parses_then_runs_duplicate_acceptance_gate_before_storage() -> None:
    source = _service_source()
    start = source.index("def ingest_receipt(")
    end = source.index("def _resolve_reparse_source_payload(", start)
    block = source[start:end]

    parse_index = block.index("scan_receipt_content_via_gateway(")
    candidate_index = block.index("StructuredReceiptDuplicateCandidate(")
    duplicate_index = block.index("evaluate_structured_receipt_duplicate(")
    storage_index = block.index("_store_raw_file(")

    assert parse_index < candidate_index < duplicate_index < storage_index
    assert "find_existing_receipt_by_content_hash(" not in block
    assert "find_existing_receipt_by_fingerprint(" not in block
