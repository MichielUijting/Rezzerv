"""ONE-OFF architecture proof for PR557 receipt duplicate guard extraction.

Not wired to a dedicated recurring workflow. This is one atomic proof: the green
marker is emitted only after ownership, scanner-independence, acceptance order,
legacy decision equivalence, household/lifecycle invariants and mutation
sensitivity have all passed.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services import receipt_duplicate_guard as guard
from app.services.receipt_duplicate_guard import StructuredReceiptDuplicateCandidate


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
SERVICE_PATH = APP_ROOT / "services" / "receipt_service.py"
GUARD_PATH = APP_ROOT / "services" / "receipt_duplicate_guard.py"

DUPLICATE_DEFINITION_TOKENS = (
    "def find_existing_receipt_by_content_hash(",
    "def find_existing_receipt_by_fingerprint(",
    "def _blocks_receipt_reimport(",
    "_REIMPORT_ALLOWED_WORKFLOW_STATES =",
)

# Frozen contract facts taken from the pre-refactor implementation.
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


def _candidate() -> StructuredReceiptDuplicateCandidate:
    return StructuredReceiptDuplicateCandidate(
        source_sha256="a" * 64,
        store_name="Albert Heijn",
        purchase_at="2026-10-06T12:30:00",
        total_amount=Decimal("12.34"),
        lines=(
            {"normalized_label": "Melk", "line_total": 2.49},
            {"normalized_label": "Brood", "line_total": 3.15},
        ),
    )


def test_one_off_duplicate_guard_refactor_proof(monkeypatch, capsys) -> None:
    guard_source = _read(GUARD_PATH)
    service_source = _read(SERVICE_PATH)

    # 1. Exactly one implementation authority in backend/app.
    for token in DUPLICATE_DEFINITION_TOKENS:
        owners = []
        for path in APP_ROOT.rglob("*.py"):
            if token in _read(path):
                owners.append(path.relative_to(REPO_ROOT).as_posix())
        assert owners == ["backend/app/services/receipt_duplicate_guard.py"], (
            f"{token!r} has unexpected owners: {owners}"
        )

    # 2. The authority is scanner/parser neutral.
    lowered_guard = guard_source.lower()
    assert "receipt_scanners" not in guard_source
    assert "scan_receipt_content_via_gateway" not in guard_source
    assert "ReceiptParseResult" not in guard_source
    assert "anthropic" not in lowered_guard
    assert "inhuisdemoscanneradapter" not in lowered_guard
    assert "ocr" not in lowered_guard

    # 3. Pre-refactor household/lifecycle behavior is preserved.
    for invariant in LEGACY_INVARIANTS:
        assert invariant in guard_source
    fingerprint_block = guard_source[
        guard_source.index("def find_existing_receipt_by_fingerprint("):
        guard_source.index("def evaluate_structured_receipt_duplicate(")
    ]
    assert "rt.deleted_at IS NULL" not in fingerprint_block

    # 4. Structuring occurs first; duplicate acceptance gate occurs before storage.
    _assert_acceptance_order(service_source)

    # A source-level mutant that bypasses the guard must be rejected by the proof.
    mutated_service = service_source.replace(
        "duplicate_assessment = evaluate_structured_receipt_duplicate(",
        "duplicate_assessment = disabled_duplicate_guard(",
        1,
    )
    with pytest.raises((AssertionError, ValueError)):
        _assert_acceptance_order(mutated_service)

    candidate = _candidate()
    exact_existing = {
        "raw_receipt_id": "raw-exact",
        "receipt_table_id": "receipt-exact",
    }
    fingerprint_existing = {
        "raw_receipt_id": "raw-fingerprint",
        "receipt_table_id": "receipt-fingerprint",
    }

    # 5a. Legacy decision equivalence: exact hash blocks immediately.
    seen = []
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_content_hash",
        lambda conn, household_id, sha: (
            seen.append(("hash", household_id, sha)) or exact_existing
        ),
    )

    def fingerprint_must_not_run(*args, **kwargs):
        raise AssertionError("legacy contract: fingerprint must not run after exact duplicate")

    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_fingerprint",
        fingerprint_must_not_run,
    )
    result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-a",
        candidate=candidate,
    )
    assert result.is_duplicate is True
    assert result.reason == "content_hash"
    assert result.existing_receipt == exact_existing
    assert seen == [("hash", "household-a", candidate.source_sha256)]

    # 5b. Legacy decision equivalence: content differs, structured fingerprint blocks.
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_content_hash",
        lambda conn, household_id, sha: None,
    )
    fingerprint_calls = []

    def fingerprint_lookup(conn, household_id, fingerprint):
        fingerprint_calls.append((household_id, fingerprint))
        return fingerprint_existing

    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_fingerprint",
        fingerprint_lookup,
    )
    result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-b",
        candidate=candidate,
    )
    assert result.is_duplicate is True
    assert result.reason == "structured_fingerprint"
    assert result.existing_receipt == fingerprint_existing
    assert fingerprint_calls[0][0] == "household-b"
    assert "albert heijn" in fingerprint_calls[0][1]
    assert "12.34" in fingerprint_calls[0][1]

    # 5c. Legacy decision equivalence: neither barrier matches, so accept.
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_content_hash",
        lambda conn, household_id, sha: None,
    )
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_fingerprint",
        lambda conn, household_id, fingerprint: None,
    )
    result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-c",
        candidate=candidate,
    )
    assert result.is_duplicate is False
    assert result.reason is None
    assert result.fingerprint

    # 6. Mutation sensitivity: disabling both barriers changes reject -> accept.
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_content_hash",
        lambda conn, household_id, sha: exact_existing,
    )
    real_result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-mutation",
        candidate=candidate,
    )
    assert real_result.is_duplicate is True

    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_content_hash",
        lambda conn, household_id, sha: None,
    )
    monkeypatch.setattr(
        guard,
        "find_existing_receipt_by_fingerprint",
        lambda conn, household_id, fingerprint: None,
    )
    mutant_result = guard.evaluate_structured_receipt_duplicate(
        object(),
        household_id="household-mutation",
        candidate=candidate,
    )
    assert mutant_result.is_duplicate is False
    assert real_result.is_duplicate != mutant_result.is_duplicate

    # Marker is intentionally last: it cannot be emitted if any proof above fails.
    print("DUPLICATE_GUARD_REFACTOR_PROOF_GREEN")
    captured = capsys.readouterr()
    assert captured.out.strip() == "DUPLICATE_GUARD_REFACTOR_PROOF_GREEN"
