from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_service.py"


def _service_source() -> str:
    return SERVICE_PATH.read_text(encoding="utf-8")


def test_global_receipt_dedupe_blocks_all_non_removed_lifecycle_states() -> None:
    source = _service_source()

    assert "_REIMPORT_ALLOWED_WORKFLOW_STATES = {'removed_reimport_allowed', 'legacy_deleted'}" in source
    assert "def _blocks_receipt_reimport(workflow_state: str | None) -> bool:" in source
    assert "return normalized not in _REIMPORT_ALLOWED_WORKFLOW_STATES" in source


def test_exact_content_hash_dedupe_is_household_scoped_and_lifecycle_aware() -> None:
    source = _service_source()
    start = source.index("def find_existing_receipt_by_content_hash(")
    end = source.index("def find_existing_receipt_by_fingerprint(", start)
    block = source[start:end]

    assert "rr.household_id = :household_id" in block
    assert "rr.sha256_hash = :sha256_hash" in block
    assert "removed_reimport_allowed" in block
    assert "legacy_deleted" in block
    assert "rr.updated_at" not in block


def test_cross_source_fingerprint_dedupe_keeps_archived_and_processed_history() -> None:
    source = _service_source()
    start = source.index("def find_existing_receipt_by_fingerprint(")
    end = source.index("def dedupe_receipts_for_household(", start)
    block = source[start:end]

    assert "rt.household_id = :household_id" in block
    assert "removed_reimport_allowed" in block
    assert "legacy_deleted" in block
    assert "rt.deleted_at IS NULL" not in block
    assert "_fingerprint_from_stored_receipt(" in block


def test_ingest_checks_exact_hash_before_parsing_and_fingerprint_after_parsing() -> None:
    source = _service_source()
    start = source.index("def ingest_receipt(")
    end = source.index("def _resolve_reparse_source_payload(", start)
    block = source[start:end]

    exact_index = block.index("find_existing_receipt_by_content_hash(")
    parse_index = block.index("scan_receipt_content_via_gateway(")
    fingerprint_index = block.index("find_existing_receipt_by_fingerprint(")

    assert exact_index < parse_index < fingerprint_index
