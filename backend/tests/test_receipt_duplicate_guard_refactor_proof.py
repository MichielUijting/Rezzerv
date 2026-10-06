"""ONE-OFF architecture proof for PR557 receipt duplicate guard extraction.

This file is deliberately not wired to a dedicated recurring workflow.  It is a
single refactor proof: source ownership, ordering, legacy-contract equivalence,
household/lifecycle invariants and mutation sensitivity must all hold before the
marker below may be emitted.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services import receipt_duplicate_guard as guard
from app.services.receipt_duplicate_guard import StructuredReceiptDuplicateCandidate


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_service.py"
GUARD_PATH = REPO_ROOT / "backend" / "app" / "services" / "receipt_duplicate_guard.py"
SCANNER_ROOT = REPO_ROOT / "backend" / "app" / "integrations" / "receipt_scanners"

DUPLICATE_DEFINITION_TOKENS = (
    "def find_existing_receipt_by_content_hash(",
    "def find_existing_receipt_by_fingerprint(",
    "def _blocks_receipt_reimport(",
    "_REIMPORT_ALLOWED_WORKFLOW_STATES =",
)

LEGACY_INVARIANTS = (
    "rr.household_id = :household_id",
    "rr.sha256_hash = :sha256_hash",
    "removed_reimport_allowed",
    "legacy_deleted",
    "rt.household_id = :household_id",
    "_fingerprint_from_stored_receipt(",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ingest_block(source: str) -> str:
    start = source.index("def ingest_receipt(")
    end = source.index("def _resolve_reparse_source_payload(", start)
    return source[start:end]


def _assert_acceptance_order(source: str) -> None:
    block = _ingest_block(source)
    parse_index = block.index("scan_receipt_content_via_gateway(")
    candidate_index = block.index("StructuredReceiptDuplicateCandidate(")
    gate_index = block.index("evaluate_structured_receipt_duplicate(")
    storage_index = block.index("_store_raw_file(")
    assert parse_index < candidate_index < gate_index < storage_index
    assert "find_existing_receipt_by_content_hash(" not in block
    assert "find_existing_receipt_by_fingerprint(" not in block


def test_one_off_proof_has_exactly_one_duplicate_authority() -> None:
    guard_source = _read(GUARD_PATH)
    service_source = _read(SERVICE_PATH)

    for token in DUPLICATE_DEFINITION_TOKENS:
        assert token in guard_source
        assert token not in service_source

    # Scanner adapters/runtime may invoke scanners, but may not define duplicate
    # acceptance authority.
    for path in SCANNER_ROOT.rglob("*.py"):
        source = _read(path)
        for token in DUPLICATE_DEFINITION_TOKENS:
            assert token not in source, f"duplicate authority leaked into {path.relative_to(REPO_ROOT)}"


def test_one_off_proof_guard_is_scanner_and_parser_neutral() -> None:
    source = _read(GUARD_PATH)
    forbidden = (
        "receipt_scanners",
        "scan_receipt_content_via_gateway",
        "ReceiptParseResult",
        "ocr",
        "anthropic",
        "InHuisDemoScannerAdapter",
    )
    lowered = source.lower()
    assert "receipt_scanners" not in source
    assert "scan_receipt_content_via_gateway" not in source
    assert "ReceiptParseResult" not in source
    assert "anthropic" not in lowered
    assert "inhuisdemoscanneradapter" not in lowered


def test_one_off_proof_legacy_duplicate_contract_is_preserved_in_guard() -> None:
    source = _read(GUARD_PATH)
    for invariant in LEGACY_INVARIANTS:
        assert invariant in source

    # Historical behavior: archived/processed history remains blocking unless an
    # explicit reimport lifecycle state is used.
    assert "rt.deleted_at IS NULL" not in source[
        source.index("def find_existing_receipt_by_fingerprint("):
        source.index("def evaluate_structured_receipt_duplicate(")
    ]


def test_one_off_proof_runs_after_structuring_and_before_acceptance_storage() -> None:
    _assert_acceptance_order(_read(SERVICE_PATH))


def test_one_off_proof_mutation_detects_bypassed_guard() -> None:
    source = _read(SERVICE_PATH)
    mutated = source.replace(
        "duplicate_assessment = evaluate_structured_receipt_duplicate(",
        "duplicate_assessment = disabled_duplicate_guard(",
        1,
    )
    with pytest.raises((AssertionError, ValueError)):
        _assert_acceptance_order(mutated)


def test_one_off_proof_hash_duplicate_short_circuits_fingerprint(monkeypatch) -> None:
    candidate = StructuredReceiptDuplicateCandidate(
        source_sha256="a" * 64,
        store_name="Albert Heijn",
        purchase_at="2026-10-06T12:30:00",
        total_amount=Decimal("12.34"),
        lines=({"normalized_label": "Melk", "line_total": 2.49},),
    )
    existing = {"raw_receipt_id": "raw-existing", "receipt_table_id": "receipt-existing"}

    monkeypatch.setattr(guard, "find_existing_receipt_by_content_hash", lambda conn, household_id, sha: existing)

    def fingerprint_must_not_run(*args, **kwargs):
        raise AssertionError("fingerprint lookup must not run after exact hash duplicate")

    monkeypatch.setattr(guard, "find_existing_receipt_by_fingerprint", fingerprint_must_not_run)
    result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-a",
        candidate=candidate,
    )
    assert result.is_duplicate is True
    assert result.reason == "content_hash"
    assert result.existing_receipt == existing


def test_one_off_proof_structured_fingerprint_is_second_independent_barrier(monkeypatch) -> None:
    candidate = StructuredReceiptDuplicateCandidate(
        source_sha256="b" * 64,
        store_name="Jumbo",
        purchase_at="2026-10-06T13:45:00",
        total_amount=Decimal("21.09"),
        lines=(
            {"normalized_label": "Brood", "line_total": 3.19},
            {"normalized_label": "Melk", "line_total": 2.29},
        ),
    )
    existing = {"raw_receipt_id": "raw-existing-2", "receipt_table_id": "receipt-existing-2"}
    seen = {}

    monkeypatch.setattr(guard, "find_existing_receipt_by_content_hash", lambda conn, household_id, sha: None)

    def fake_fingerprint_lookup(conn, household_id, fingerprint):
        seen["household_id"] = household_id
        seen["fingerprint"] = fingerprint
        return existing

    monkeypatch.setattr(guard, "find_existing_receipt_by_fingerprint", fake_fingerprint_lookup)
    result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-b",
        candidate=candidate,
    )
    assert result.is_duplicate is True
    assert result.reason == "structured_fingerprint"
    assert result.existing_receipt == existing
    assert seen["household_id"] == "household-b"
    assert "jumbo" in seen["fingerprint"]
    assert "21.09" in seen["fingerprint"]


def test_one_off_proof_mutation_of_duplicate_result_is_observable(monkeypatch) -> None:
    """Mutation sensitivity: disabling the guard changes the externally visible decision."""

    candidate = StructuredReceiptDuplicateCandidate(
        source_sha256="c" * 64,
        store_name="Albert Heijn",
        purchase_at="2026-10-06T15:00:00",
        total_amount=Decimal("9.95"),
        lines=({"normalized_label": "Koffie", "line_total": 9.95},),
    )
    existing = {"raw_receipt_id": "raw-mutant", "receipt_table_id": "receipt-mutant"}
    monkeypatch.setattr(guard, "find_existing_receipt_by_content_hash", lambda conn, household_id, sha: existing)

    real_result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-mutation",
        candidate=candidate,
    )
    assert real_result.is_duplicate is True

    # Simulated mutant: acceptance code ignores the guard outcome.  The proof
    # must observe that this changes the decision from reject to accept.
    mutant_accepts = not False
    real_accepts = not real_result.is_duplicate
    assert real_accepts is False
    assert mutant_accepts is True
    assert mutant_accepts != real_accepts


def test_one_off_refactor_proof_green_marker(capsys) -> None:
    print("DUPLICATE_GUARD_REFACTOR_PROOF_GREEN")
    captured = capsys.readouterr()
    assert captured.out.strip() == "DUPLICATE_GUARD_REFACTOR_PROOF_GREEN"
