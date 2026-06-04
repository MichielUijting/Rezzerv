from __future__ import annotations

import base64
import copy
import json
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.services.receipt_service import detect_mime_type, parse_receipt_content

router = APIRouter()

REGRESSION_ROOT = Path(__file__).resolve().parents[2] / "testing" / "kassa_regression"
MANIFEST_PATH = REGRESSION_ROOT / "manifest.json"
RAW_DIR = REGRESSION_ROOT / "raw"
RAW_B64_DIR = REGRESSION_ROOT / "raw_b64"
REQUIRED_CHAINS = ["Albert Heijn", "ALDI", "Jumbo", "PLUS", "Lidl", "Picnic"]
REQUIRED_RECEIPT_COUNT = 18

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _set_job_state(**updates: Any) -> None:
    with _JOB_LOCK:
        _JOB_STATE.update(updates)


def _get_job_state() -> dict[str, Any]:
    with _JOB_LOCK:
        return copy.deepcopy(_JOB_STATE)


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _line_value(line: Any, key: str) -> Any:
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _canonical_chain(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if "albert heijn" in normalized or normalized == "ah":
        return "Albert Heijn"
    if "aldi" in normalized:
        return "ALDI"
    if "jumbo" in normalized:
        return "Jumbo"
    if "plus" in normalized:
        return "PLUS"
    if "lidl" in normalized:
        return "Lidl"
    if "picnic" in normalized:
        return "Picnic"
    return None


def _load_manifest() -> tuple[dict[str, Any] | None, list[str]]:
    if not MANIFEST_PATH.exists():
        return None, [f"Manifest ontbreekt: {MANIFEST_PATH}"]
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"Manifest is ongeldig JSON: {exc}"]
    issues: list[str] = []
    cases = manifest.get("cases")
    expected_count = int(manifest.get("required_receipt_count") or REQUIRED_RECEIPT_COUNT)
    if not isinstance(cases, list):
        issues.append("Manifest bevat geen geldige cases-lijst")
    elif len(cases) != expected_count:
        issues.append(f"Manifest bevat {len(cases)} cases; verwacht {expected_count}")
    return manifest, issues


def _case_source_exists(case: dict[str, Any]) -> bool:
    filename = str(case.get("filename") or "").strip()
    b64_filename = str(case.get("b64_filename") or "").strip()
    return bool(filename and (RAW_DIR / filename).exists()) or bool(b64_filename and (RAW_B64_DIR / b64_filename).exists())


def _load_case_payload(case: dict[str, Any]) -> tuple[bytes, str]:
    filename = str(case.get("filename") or "").strip()
    b64_filename = str(case.get("b64_filename") or "").strip()
    if filename and (RAW_DIR / filename).exists():
        return (RAW_DIR / filename).read_bytes(), filename
    if b64_filename and (RAW_B64_DIR / b64_filename).exists():
        raw = (RAW_B64_DIR / b64_filename).read_text(encoding="ascii")
        return base64.b64decode(raw), filename or b64_filename.removesuffix(".b64")
    raise FileNotFoundError(f"Geen fixturebestand gevonden voor {case.get('id') or filename or b64_filename or '-'}")


def _validate_manifest_cases(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    seen_chains = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            issues.append(f"Case {index}: geen object")
            continue
        case_id = str(case.get("id") or "").strip()
        filename = str(case.get("filename") or "").strip()
        b64_filename = str(case.get("b64_filename") or "").strip()
        chain = _canonical_chain(str(case.get("chain") or ""))
        if not case_id:
            issues.append(f"Case {index}: id ontbreekt")
        if not filename and not b64_filename:
            issues.append(f"Case {case_id or index}: filename of b64_filename ontbreekt")
        elif not _case_source_exists(case):
            expected = f"raw/{filename}" if filename else f"raw_b64/{b64_filename}"
            if filename and b64_filename:
                expected = f"raw/{filename} of raw_b64/{b64_filename}"
            issues.append(f"Case {case_id or index}: bestand ontbreekt: {expected}")
        if not chain:
            issues.append(f"Case {case_id or index}: onbekende keten {case.get('chain') or '-'}")
        else:
            seen_chains.add(chain)
    for chain in REQUIRED_CHAINS:
        if chain not in seen_chains:
            issues.append(f"Keten ontbreekt in manifest: {chain}")
    return issues


def _init_test_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table raw_receipts (id text primary key, original_filename text not null, mime_type text not null, imported_at text not null);
        create table receipt_tables (id text primary key, raw_receipt_id text not null, store_name text, purchase_at text, total_amount numeric, currency text, parse_status text, line_count integer, discount_total numeric, created_at text not null);
        create table receipt_table_lines (id text primary key, receipt_table_id text not null, line_index integer not null, raw_label text, quantity numeric, unit text, unit_price numeric, line_total numeric, discount_amount numeric);
        """
    )


def _write_parse_result(conn: sqlite3.Connection, parsed: Any, filename: str, mime_type: str) -> dict[str, Any]:
    raw_id = str(uuid.uuid4())
    receipt_id = str(uuid.uuid4())
    now = _utc_now()
    lines = list(parsed.lines or [])
    conn.execute("insert into raw_receipts (id, original_filename, mime_type, imported_at) values (?, ?, ?, ?)", (raw_id, filename, mime_type, now))
    conn.execute(
        "insert into receipt_tables (id, raw_receipt_id, store_name, purchase_at, total_amount, currency, parse_status, line_count, discount_total, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (receipt_id, raw_id, parsed.store_name, parsed.purchase_at, _decimal_to_float(parsed.total_amount), parsed.currency or "EUR", parsed.parse_status, len(lines), _decimal_to_float(parsed.discount_total), now),
    )
    for index, line in enumerate(lines, start=1):
        conn.execute(
            "insert into receipt_table_lines (id, receipt_table_id, line_index, raw_label, quantity, unit, unit_price, line_total, discount_amount) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), receipt_id, index, _line_value(line, "raw_label"), _decimal_to_float(_line_value(line, "quantity")), _line_value(line, "unit"), _decimal_to_float(_line_value(line, "unit_price")), _decimal_to_float(_line_value(line, "line_total")), _decimal_to_float(_line_value(line, "discount_amount"))),
        )
    return {"raw_receipt_id": raw_id, "receipt_table_id": receipt_id, "line_count": len(lines)}


def _case_expected_ok(case: dict[str, Any], parsed: Any, persisted: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    expected_chain = _canonical_chain(str(case.get("chain") or ""))
    found_chain = _canonical_chain(str(parsed.store_name or ""))
    if expected_chain and found_chain != expected_chain:
        issues.append(f"winkel verwacht {expected_chain}, gevonden {parsed.store_name or '-'}")
    if case.get("expected_total") is not None:
        expected_total = round(float(case.get("expected_total")), 2)
        found_total = _decimal_to_float(parsed.total_amount)
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


def _missing_source_report(manifest: dict[str, Any] | None, issues: list[str]) -> dict[str, Any]:
    return {
        "test_type": "kassa_receipt_regression",
        "status": "blocked",
        "ran_at": _utc_now(),
        "acceptance_basis": "Geblokkeerd: de vaste baseline V8-regressieset ontbreekt of is onvolledig.",
        "summary": {"required_receipt_count": (manifest or {}).get("required_receipt_count") or REQUIRED_RECEIPT_COUNT, "tested_receipt_count": 0, "passed_count": 0, "failed_count": 0, "blocked_count": len(issues)},
        "chains": [],
        "results": [],
        "blocking_issues": issues,
    }


def _build_final_report(results: list[dict[str, Any]]) -> dict[str, Any]:
    chains = []
    for chain in REQUIRED_CHAINS:
        chain_results = [item for item in results if item.get("chain") == chain]
        failed = [item for item in chain_results if item.get("status") != "passed"]
        chains.append({"chain": chain, "status": "missing" if not chain_results else ("failed" if failed else "passed"), "receipt_count": len(chain_results), "passed_count": len(chain_results) - len(failed), "failed_count": len(failed), "failures": failed})
    failed_count = sum(1 for item in results if item.get("status") != "passed")
    passed_count = sum(1 for item in results if item.get("status") == "passed")
    return {
        "test_type": "kassa_receipt_regression",
        "status": "passed" if failed_count == 0 and len(results) == REQUIRED_RECEIPT_COUNT else "failed",
        "ran_at": _utc_now(),
        "acceptance_basis": "Baseline V8: 18 vaste testkassabonnen inclusief Picnic worden opnieuw door parse_receipt_content gehaald en in een tijdelijke aparte SQLite-testdatabase geschreven. Datum/tijd wordt nooit gevalideerd.",
        "summary": {"required_receipt_count": REQUIRED_RECEIPT_COUNT, "tested_receipt_count": len(results), "passed_count": passed_count, "failed_count": failed_count, "blocked_count": 0},
        "chains": chains,
        "results": results,
        "blocking_issues": [],
    }


def _execute_kassa_regression_job(job_id: str) -> None:
    try:
        manifest, manifest_issues = _load_manifest()
        if manifest is None:
            report = _missing_source_report(manifest, manifest_issues)
            _set_job_state(status="blocked", finished_at=_utc_now(), message="Regressieset ontbreekt", report=report)
            return
        case_issues = _validate_manifest_cases(manifest)
        if manifest_issues or case_issues:
            report = _missing_source_report(manifest, manifest_issues + case_issues)
            _set_job_state(status="blocked", finished_at=_utc_now(), message="Regressieset onvolledig", report=report)
            return
        cases = manifest.get("cases") or []
        results: list[dict[str, Any]] = []
        _set_job_state(progress_total=len(cases), message="Regressie gestart")
        with tempfile.NamedTemporaryFile(prefix="rezzerv_kassa_regression_", suffix=".sqlite", delete=True) as tmp:
            conn = sqlite3.connect(tmp.name)
            try:
                _init_test_database(conn)
                for index, case in enumerate(cases, start=1):
                    case_id = str(case.get("id") or f"case_{index}")
                    chain = _canonical_chain(str(case.get("chain") or "")) or str(case.get("chain") or "Onbekend")
                    display_filename = str(case.get("filename") or case.get("b64_filename") or "")
                    _set_job_state(status="running", progress_current=index - 1, progress_total=len(cases), current_case_id=case_id, current_filename=display_filename, message=f"Bon {index} van {len(cases)} verwerken: {case_id}")
                    try:
                        payload, filename = _load_case_payload(case)
                        mime_type = str(case.get("mime_type") or detect_mime_type(filename, payload))
                        parsed = parse_receipt_content(payload, filename, mime_type)
                        persisted = _write_parse_result(conn, parsed, filename, mime_type)
                        ok, issues = _case_expected_ok(case, parsed, persisted)
                        results.append({"case_id": case_id, "chain": chain, "filename": filename, "status": "passed" if ok else "failed", "error": "; ".join(issues) if issues else None, "details": {**persisted, "store_found": parsed.store_name, "purchase_found": parsed.purchase_at, "total_found": _decimal_to_float(parsed.total_amount), "parse_status": parsed.parse_status}})
                    except Exception as exc:
                        results.append({"case_id": case_id, "chain": chain, "filename": display_filename, "status": "failed", "error": f"technische fout tijdens inlezen: {exc}", "details": {}})
                    _set_job_state(progress_current=index, message=f"Bon {index} van {len(cases)} afgerond")
                conn.commit()
            finally:
                conn.close()
        report = _build_final_report(results)
        _set_job_state(status=report["status"], finished_at=_utc_now(), progress_current=len(cases), current_case_id=None, current_filename=None, message="Regressie afgerond", report=report)
    except Exception as exc:
        report = _missing_source_report(None, [f"Technische fout in regressiejob: {exc}"])
        _set_job_state(status="blocked", finished_at=_utc_now(), message=f"Technische fout: {exc}", report=report)


@router.post("/api/admin/kassa-regression/run")
def start_kassa_receipt_regression() -> dict[str, Any]:
    with _JOB_LOCK:
        if _JOB_STATE.get("status") == "running":
            return copy.deepcopy(_JOB_STATE)
        job_id = uuid.uuid4().hex
        _JOB_STATE.update({"job_id": job_id, "status": "running", "started_at": _utc_now(), "finished_at": None, "progress_current": 0, "progress_total": REQUIRED_RECEIPT_COUNT, "current_case_id": None, "current_filename": None, "message": "Regressie wordt gestart", "report": None})
    threading.Thread(target=_execute_kassa_regression_job, args=(job_id,), daemon=True).start()
    return _get_job_state()


@router.get("/api/admin/kassa-regression/status")
def get_kassa_receipt_regression_status() -> dict[str, Any]:
    return _get_job_state()
