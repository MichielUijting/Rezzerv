from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.api.routes import kassa_regression_routes as regression
from app.services.receipt_service import detect_mime_type, parse_receipt_content

router = APIRouter()

SMOKE_MANIFEST_PATH = regression.REGRESSION_ROOT / "smoke_manifest.json"
REQUIRED_CHAINS = ["Albert Heijn", "ALDI", "Jumbo", "PLUS", "Lidl"]
REQUIRED_RECEIPT_COUNT = 5

_JOB_LOCK = threading.Lock()
_JOB_STATE: dict[str, Any] = {
    "job_id": None,
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "progress_current": 0,
    "progress_total": REQUIRED_RECEIPT_COUNT,
    "current_case_id": None,
    "current_filename": None,
    "message": "Nog niet gestart",
    "report": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set_state(**updates: Any) -> None:
    with _JOB_LOCK:
        _JOB_STATE.update(updates)


def _state() -> dict[str, Any]:
    with _JOB_LOCK:
        return copy.deepcopy(_JOB_STATE)


def _load_manifest() -> tuple[dict[str, Any] | None, list[str]]:
    if not SMOKE_MANIFEST_PATH.exists():
        return None, [f"Smoke manifest ontbreekt: {SMOKE_MANIFEST_PATH}"]
    try:
        manifest = json.loads(SMOKE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"Smoke manifest is ongeldig JSON: {exc}"]
    issues: list[str] = []
    cases = manifest.get("cases")
    expected_count = int(manifest.get("required_receipt_count") or REQUIRED_RECEIPT_COUNT)
    if not isinstance(cases, list):
        issues.append("Smoke manifest bevat geen geldige cases-lijst")
    elif len(cases) != expected_count:
        issues.append(f"Smoke manifest bevat {len(cases)} cases; verwacht {expected_count}")
    return manifest, issues


def _validate_manifest(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    seen_chains = set()
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            issues.append(f"Case {index}: geen object")
            continue
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            issues.append(f"Case {index}: id ontbreekt")
        if not regression._case_source_exists(case):
            expected = str(case.get("filename") or case.get("b64_filename") or "-")
            issues.append(f"Case {case_id or index}: bestand ontbreekt: {expected}")
        canonical = regression._canonical_chain(str(case.get("chain") or ""))
        if not canonical:
            issues.append(f"Case {case_id or index}: onbekende keten {case.get('chain') or '-'}")
        else:
            seen_chains.add(canonical)
    for required in REQUIRED_CHAINS:
        if required not in seen_chains:
            issues.append(f"Keten ontbreekt in smoke manifest: {required}")
    return issues


def _case_ok(case: dict[str, Any], parsed: Any, persisted: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    expected_chain = regression._canonical_chain(str(case.get("chain") or ""))
    found_chain = regression._canonical_chain(str(parsed.store_name or ""))
    if expected_chain and found_chain != expected_chain:
        issues.append(f"winkel verwacht {expected_chain}, gevonden {parsed.store_name or '-'}")
    if case.get("expected_total") is not None:
        expected_total = round(float(case.get("expected_total")), 2)
        found_total = regression._decimal_to_float(parsed.total_amount)
        if found_total is None or round(float(found_total), 2) != expected_total:
            issues.append(f"totaal verwacht {expected_total:.2f}, gevonden {found_total if found_total is not None else '-'}")
    elif parsed.total_amount is None:
        issues.append("totaalbedrag ontbreekt")
    expected_min_lines = int(case.get("expected_min_line_count") or 1)
    if int(persisted.get("line_count") or 0) < expected_min_lines:
        issues.append(f"artikelregels verwacht minimaal {expected_min_lines}, gevonden {persisted.get('line_count') or 0}")
    if str(parsed.parse_status or "").strip().lower() in {"failed", "error"}:
        issues.append(f"parse_status {parsed.parse_status}")
    return not issues, issues


def _blocked_report(manifest: dict[str, Any] | None, issues: list[str]) -> dict[str, Any]:
    return {
        "test_type": "kassa_smoke_check",
        "status": "blocked",
        "ran_at": _now(),
        "acceptance_basis": "Geblokkeerd: de minimale 5-bonnen Kassa-controleset ontbreekt of is onvolledig.",
        "summary": {
            "required_receipt_count": (manifest or {}).get("required_receipt_count") or REQUIRED_RECEIPT_COUNT,
            "tested_receipt_count": 0,
            "passed_count": 0,
            "failed_count": 0,
            "blocked_count": len(issues),
        },
        "chains": [],
        "results": [],
        "blocking_issues": issues,
    }


def _final_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    chains = []
    for chain in REQUIRED_CHAINS:
        items = [item for item in results if item.get("chain") == chain]
        failures = [item for item in items if item.get("status") != "passed"]
        chains.append({
            "chain": chain,
            "status": "missing" if not items else ("failed" if failures else "passed"),
            "receipt_count": len(items),
            "passed_count": len(items) - len(failures),
            "failed_count": len(failures),
            "failures": failures,
        })
    failed_count = sum(1 for item in results if item.get("status") != "passed")
    passed_count = sum(1 for item in results if item.get("status") == "passed")
    return {
        "test_type": "kassa_smoke_check",
        "status": "passed" if failed_count == 0 and len(results) == REQUIRED_RECEIPT_COUNT else "failed",
        "ran_at": _now(),
        "acceptance_basis": "5 vaste testkassabonnen, 1 per winkelketen, worden opnieuw door parse_receipt_content gehaald en in een tijdelijke aparte SQLite-testdatabase geschreven. Datum/tijd wordt nooit gevalideerd.",
        "summary": {
            "required_receipt_count": REQUIRED_RECEIPT_COUNT,
            "tested_receipt_count": len(results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "blocked_count": 0,
        },
        "chains": chains,
        "results": results,
        "blocking_issues": [],
    }


def _run_job(job_id: str) -> None:
    try:
        manifest, manifest_issues = _load_manifest()
        if manifest is None:
            report = _blocked_report(manifest, manifest_issues)
            _set_state(status="blocked", finished_at=_now(), message="Smoke-set ontbreekt", report=report)
            return
        case_issues = _validate_manifest(manifest)
        if manifest_issues or case_issues:
            report = _blocked_report(manifest, manifest_issues + case_issues)
            _set_state(status="blocked", finished_at=_now(), message="Smoke-set onvolledig", report=report)
            return
        cases = manifest.get("cases") or []
        results: list[dict[str, Any]] = []
        _set_state(progress_total=len(cases), message="Kassa smoke-check gestart")
        with tempfile.NamedTemporaryFile(prefix="rezzerv_kassa_smoke_", suffix=".sqlite", delete=True) as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                regression._init_test_database(conn)
                for index, case in enumerate(cases, start=1):
                    case_id = str(case.get("id") or f"case_{index}")
                    chain = regression._canonical_chain(str(case.get("chain") or "")) or str(case.get("chain") or "Onbekend")
                    display_filename = str(case.get("filename") or case.get("b64_filename") or "")
                    _set_state(status="running", progress_current=index - 1, progress_total=len(cases), current_case_id=case_id, current_filename=display_filename, message=f"Bon {index} van {len(cases)} verwerken: {case_id}")
                    try:
                        payload, filename = regression._load_case_payload(case)
                        mime_type = str(case.get("mime_type") or detect_mime_type(filename, payload))
                        parsed = parse_receipt_content(payload, filename, mime_type)
                        persisted = regression._write_parse_result(conn, case, parsed, filename, mime_type)
                        ok, issues = _case_ok(case, parsed, persisted)
                        results.append({
                            "case_id": case_id,
                            "chain": chain,
                            "filename": filename,
                            "status": "passed" if ok else "failed",
                            "error": "; ".join(issues) if issues else None,
                            "details": {
                                **persisted,
                                "store_found": parsed.store_name,
                                "purchase_found": parsed.purchase_at,
                                "total_found": regression._decimal_to_float(parsed.total_amount),
                                "parse_status": parsed.parse_status,
                            },
                        })
                    except Exception as exc:
                        results.append({"case_id": case_id, "chain": chain, "filename": display_filename, "status": "failed", "error": f"technische fout tijdens inlezen: {exc}", "details": {}})
                    _set_state(progress_current=index, message=f"Bon {index} van {len(cases)} afgerond")
                conn.commit()
            finally:
                conn.close()
        report = _final_report(results)
        _set_state(status=report["status"], finished_at=_now(), progress_current=len(cases), current_case_id=None, current_filename=None, message="Kassa smoke-check afgerond", report=report)
    except Exception as exc:
        report = _blocked_report(None, [f"Technische fout in smoke-check: {exc}"])
        _set_state(status="blocked", finished_at=_now(), message=f"Technische fout: {exc}", report=report)


@router.post("/api/admin/kassa-smoke/run")
def start_kassa_smoke_check() -> dict[str, Any]:
    with _JOB_LOCK:
        if _JOB_STATE.get("status") == "running":
            return copy.deepcopy(_JOB_STATE)
        job_id = uuid.uuid4().hex
        _JOB_STATE.update({
            "job_id": job_id,
            "status": "running",
            "started_at": _now(),
            "finished_at": None,
            "progress_current": 0,
            "progress_total": REQUIRED_RECEIPT_COUNT,
            "current_case_id": None,
            "current_filename": None,
            "message": "Kassa smoke-check wordt gestart",
            "report": None,
        })
    threading.Thread(target=_run_job, args=(job_id,), daemon=True).start()
    return _state()


@router.get("/api/admin/kassa-smoke/status")
def get_kassa_smoke_check_status() -> dict[str, Any]:
    return _state()
