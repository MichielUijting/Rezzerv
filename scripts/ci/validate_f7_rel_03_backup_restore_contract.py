#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "quality/ci/f7_rel_03_backup_restore_contract.json"
MAP = ROOT / "quality/ci/f7_ci_orchestration_gate_map.json"
WORKFLOW = ROOT / ".github/workflows/f7-rel-03-backup-restore-postgresql-authority.yml"

EXPECTED_MARKERS = [
    "F7_REL_03_CANDIDATE_IDENTITY_GREEN",
    "F7_REL_03_SOURCE_SCHEMA_GREEN",
    "F7_REL_03_BACKUP_CREATED_GREEN",
    "F7_REL_03_RESTORE_GREEN",
    "F7_REL_03_RESTORED_BOUNDARY_GREEN",
    "F7_REL_03_STARTUP_GREEN",
    "F7_REL_03_DATA_INTEGRITY_GREEN",
    "F7_REL_03_BACKUP_RESTORE_GATE_GREEN",
]


def require(condition: bool, marker: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL {marker}")
    print(f"PASS {marker}")


def load(path: Path) -> dict:
    require(path.is_file(), f"exists_{path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    contract = load(CONTRACT)
    gate_map = load(MAP)
    workflow = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.is_file() else ""

    require(contract.get("schema_version") == 1, "f7_rel_03_contract_schema")
    require(contract.get("authority_id") == "F7-REL-03", "f7_rel_03_authority_id")
    require(contract.get("status") in {"in_progress", "closed"}, "f7_rel_03_status_valid")
    require(contract.get("target_base") == "main", "f7_rel_03_target_main")
    require(contract.get("postgresql_major") == 17, "f7_rel_03_postgresql_17")
    require(contract.get("source_database") != contract.get("restore_database"), "f7_rel_03_distinct_databases")

    candidate = contract.get("candidate_policy") or {}
    require(candidate.get("pull_request_actions") == ["opened", "reopened", "ready_for_review", "synchronize"], "f7_rel_03_pr_actions")
    require(candidate.get("draft_behavior") == "skip_heavy_authority", "f7_rel_03_draft_guard_contract")
    require(candidate.get("exact_sha_required") is True, "f7_rel_03_exact_sha_contract")

    backup = contract.get("backup_policy") or {}
    require(backup.get("tool") == "pg_dump", "f7_rel_03_pg_dump_contract")
    require(backup.get("format") == "custom", "f7_rel_03_custom_dump_contract")
    require(set(backup.get("flags") or []) == {"--no-owner", "--no-acl"}, "f7_rel_03_dump_flags_contract")

    restore = contract.get("restore_policy") or {}
    require(restore.get("tool") == "pg_restore", "f7_rel_03_pg_restore_contract")
    require(restore.get("target") == "fresh empty database", "f7_rel_03_fresh_restore_contract")
    require(set(restore.get("flags") or []) == {"--no-owner", "--no-acl", "--exit-on-error"}, "f7_rel_03_restore_flags_contract")

    startup = contract.get("startup_policy") or {}
    require(startup.get("image") == "backend/Dockerfile", "f7_rel_03_real_backend_image")
    require(startup.get("database") == "restored database", "f7_rel_03_startup_on_restore")
    require(startup.get("http_probe") == "/openapi.json", "f7_rel_03_http_probe_contract")

    integrity = contract.get("integrity_policy") or {}
    for key in (
        "repository_alembic_head_must_match",
        "runtime_role_remains_dml_only",
        "migrator_role_retains_schema_create",
        "schema_table_count_preserved",
        "source_restore_snapshot_exact_match",
        "restore_post_start_snapshot_exact_match",
    ):
        require(integrity.get(key) is True, f"f7_rel_03_integrity_{key}")
    require(set(integrity.get("typed_integrity_probe_preserved") or []) == {"uuid", "text", "numeric", "timestamptz", "jsonb", "bytea"}, "f7_rel_03_typed_probe_contract")
    require(contract.get("required_markers") == EXPECTED_MARKERS, "f7_rel_03_markers_exact")

    release_gate = (gate_map.get("gates") or {}).get("release_acceptance") or {}
    require(release_gate.get("status") == "partial", "f7_rel_03_release_gate_remains_partial")
    residuals = {row.get("id"): row for row in release_gate.get("residuals", [])}
    require(set(residuals) == {"F7-REL-01", "F7-REL-02", "F7-REL-03"}, "f7_rel_03_release_residual_set")
    rel03 = residuals["F7-REL-03"]
    if contract.get("status") == "in_progress":
        require(rel03.get("status") in {"open", "in_progress"}, "f7_rel_03_map_not_prematurely_closed")
    else:
        require(rel03.get("status") == "closed", "f7_rel_03_map_closed")
        require(rel03.get("authority_workflow") == ".github/workflows/f7-rel-03-backup-restore-postgresql-authority.yml", "f7_rel_03_map_workflow")
        require(rel03.get("contract") == "quality/ci/f7_rel_03_backup_restore_contract.json", "f7_rel_03_map_contract")
        proof = rel03.get("proof") or {}
        require(all(proof.get(key) for key in ("run", "job", "candidate_sha", "artifact_id")), "f7_rel_03_map_proof_complete")

    require(WORKFLOW.is_file(), "f7_rel_03_workflow_exists")
    required_workflow_fragments = [
        "name: F7 REL-03 backup restore startup data-integrity authority",
        "workflow_dispatch:",
        "github.event.pull_request.draft == false",
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "pg_restore",
        "--exit-on-error",
        "CREATE DATABASE $RESTORE_DB",
        "python -m app.schema_migration_preflight",
        "python -m app.testing.postgresql_acceptance_foundation",
        "backend/Dockerfile",
        "/openapi.json",
        "f7_rel03_integrity_probe",
    ] + EXPECTED_MARKERS
    for fragment in required_workflow_fragments:
        require(fragment in workflow, f"f7_rel_03_workflow_fragment_{fragment.replace(' ', '_')[:60]}")

    print("F7_REL_03_CONTRACT_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
