from __future__ import annotations

import json
import sqlite3
import tempfile
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

REQUIRED_CHAINS = ["Albert Heijn", "ALDI", "Jumbo", "PLUS", "Lidl"]
REQUIRED_RECEIPT_COUNT = 14


def _decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


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
    return None


def _load_manifest() -> tuple[dict[str, Any] | None, list[str]]:
    issues: list[str] = []
    if not MANIFEST_PATH.exists():
        return None, [f"Manifest ontbreekt: {MANIFEST_PATH}"]
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"Manifest is ongeldig JSON: {exc}"]
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        issues.append("Manifest bevat geen geldige cases-lijst")
    elif len(cases) != int(manifest.get("required_receipt_count") or REQUIRED_RECEIPT_COUNT):
        issues.append(f"Manifest bevat {len(cases)} cases; verwacht {manifest.get('required_receipt_count') or REQUIRED_RECEIPT_COUNT}")
    return manifest, issues


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
        chain = _canonical_chain(str(case.get("chain") or ""))
        if not case_id:
            issues.append(f"Case {index}: id ontbreekt")
        if not filename:
            issues.append(f"Case {case_id or index}: filename ontbreekt")
        elif not (RAW_DIR / filename).exists():
            issues.append(f"Case {case_id or index}: bestand ontbreekt: raw/{filename}")
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
        create table raw_receipts (
            id text primary key,
            original_filename text not null,
            mime_type text not null,
            imported_at text not null
        );
        create table receipt_tables (
            id text primary key,
            raw_receipt_id text not null,
            store_name text,
            purchase_at text,
            total_amount numeric,
            currency text,
            parse_status text,
            line_count integer,
            discount_total numeric,
            created_at text not null
        );
        create table receipt_table_lines (
            id text primary key,
            receipt_table_id text not null,
            line_index integer not null,
            raw_label text,
            quantity numeric,
            unit text,
            unit_price numeric,
            line_total numeric,
            discount_amount numeric
        );
        """
    )


def _write_parse_result(conn: sqlite3.Connection, case: dict[str, Any], parsed: Any, filename: str, mime_type: str) -> dict[str, Any]:
    raw_id = str(uuid.uuid4())
    receipt_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = list(parsed.lines or [])
    conn.execute(
        "insert into raw_receipts (id, original_filename, mime_type, imported_at) values (?, ?, ?, ?)",
        (raw_id, filename, mime_type, now),
    )
    conn.execute(
        """
        insert into receipt_tables (
            id, raw_receipt_id, store_name, purchase_at, total_amount, currency,
            parse_status, line_count, discount_total, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            receipt_id,
            raw_id,
            parsed.store_name,
            parsed.purchase_at,
            _decimal_to_float(parsed.total_amount),
            parsed.currency or "EUR",
            parsed.parse_status,
            len(lines),
            _decimal_to_float(parsed.discount_total),
            now,
        ),
    )
    for index, line in enumerate(lines, start=1):
        conn.execute(
            """
            insert into receipt_table_lines (
                id, receipt_table_id, line_index, raw_label, quantity, unit,
                unit_price, line_total, discount_amount
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                receipt_id,
                index,
                getattr(line, "raw_label", None),
                _decimal_to_float(getattr(line, "quantity", None)),
                getattr(line, "unit", None),
                _decimal_to_float(getattr(line, "unit_price", None)),
                _decimal_to_float(getattr(line, "line_total", None)),
                _decimal_to_float(getattr(line, "discount_amount", None)),
            ),
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
    if case.get("expected_purchase_at"):
        expected_prefix = str(case.get("expected_purchase_at"))[:16]
        found_prefix = str(parsed.purchase_at or "")[:16]
        if found_prefix != expected_prefix:
            issues.append(f"datum/tijd verwacht {expected_prefix}, gevonden {found_prefix or '-'}")
    elif not parsed.purchase_at:
        issues.append("datum/tijd ontbreekt")
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
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "acceptance_basis": "Geblokkeerd: de vaste 14-bonnen regressieset ontbreekt of is onvolledig.",
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


@router.post("/api/admin/kassa-regression/run")
def run_kassa_receipt_regression() -> dict[str, Any]:
    manifest, manifest_issues = _load_manifest()
    if manifest is None:
        return _missing_source_report(manifest, manifest_issues)
    case_issues = _validate_manifest_cases(manifest)
    if manifest_issues or case_issues:
        return _missing_source_report(manifest, manifest_issues + case_issues)

    cases = manifest.get("cases") or []
    results: list[dict[str, Any]] = []
    chain_totals: dict[str, dict[str, int]] = {chain: {"receipt_count": 0, "passed_count": 0, "failed_count": 0} for chain in REQUIRED_CHAINS}

    with tempfile.NamedTemporaryFile(prefix="rezzerv_kassa_regression_", suffix=".sqlite", delete=True) as tmp:
        conn = sqlite3.connect(tmp.name)
        try:
            _init_test_database(conn)
            for case in cases:
                filename = str(case.get("filename") or "").strip()
                file_path = RAW_DIR / filename
                chain = _canonical_chain(str(case.get("chain") or "")) or str(case.get("chain") or "Onbekend")
                chain_totals.setdefault(chain, {"receipt_count": 0, "passed_count": 0, "failed_count": 0})
                chain_totals[chain]["receipt_count"] += 1
                try:
                    payload = file_path.read_bytes()
                    mime_type = str(case.get("mime_type") or detect_mime_type(filename, payload))
                    parsed = parse_receipt_content(payload, filename, mime_type)
                    persisted = _write_parse_result(conn, case, parsed, filename, mime_type)
                    ok, issues = _case_expected_ok(case, parsed, persisted)
                    status = "passed" if ok else "failed"
                    chain_totals[chain]["passed_count" if ok else "failed_count"] += 1
                    results.append({
                        "case_id": case.get("id"),
                        "chain": chain,
                        "filename": filename,
                        "status": status,
                        "error": "; ".join(issues) if issues else None,
                        "details": {
                            **persisted,
                            "store_found": parsed.store_name,
                            "purchase_found": parsed.purchase_at,
                            "total_found": _decimal_to_float(parsed.total_amount),
                            "parse_status": parsed.parse_status,
                        },
                    })
                except Exception as exc:
                    chain_totals[chain]["failed_count"] += 1
                    results.append({
                        "case_id": case.get("id"),
                        "chain": chain,
                        "filename": filename,
                        "status": "failed",
                        "error": f"technische fout tijdens inlezen: {exc}",
                        "details": {},
                    })
            conn.commit()
        finally:
            conn.close()

    chains = []
    for chain in REQUIRED_CHAINS:
        totals = chain_totals.get(chain, {"receipt_count": 0, "passed_count": 0, "failed_count": 0})
        status = "missing" if totals["receipt_count"] == 0 else ("failed" if totals["failed_count"] else "passed")
        failures = [item for item in results if item.get("chain") == chain and item.get("status") != "passed"]
        chains.append({
            "chain": chain,
            "status": status,
            "receipt_count": totals["receipt_count"],
            "passed_count": totals["passed_count"],
            "failed_count": totals["failed_count"],
            "failures": failures,
        })

    failed_count = sum(1 for item in results if item.get("status") != "passed")
    passed_count = sum(1 for item in results if item.get("status") == "passed")
    return {
        "test_type": "kassa_receipt_regression",
        "status": "passed" if failed_count == 0 and len(results) == REQUIRED_RECEIPT_COUNT else "failed",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "acceptance_basis": "14 vaste testkassabonnen worden opnieuw door parse_receipt_content gehaald en weggeschreven naar een tijdelijke aparte SQLite-testdatabase.",
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
