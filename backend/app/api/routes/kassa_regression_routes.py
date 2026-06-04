from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.db import engine

router = APIRouter()

REQUIRED_CHAINS = {
    "Albert Heijn": {"Albert Heijn", "AH"},
    "ALDI": {"ALDI", "Aldi"},
    "Jumbo": {"Jumbo"},
    "PLUS": {"PLUS", "Plus"},
    "Lidl": {"Lidl"},
}

PASS_STATUSES = {"approved", "parsed", "manual"}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in dict(row).items()}


def _canonical_chain(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    for canonical, aliases in REQUIRED_CHAINS.items():
        if normalized in {alias.lower() for alias in aliases}:
            return canonical
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


def _load_kassa_receipts(limit: int = 200) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = [
            _row_to_dict(row)
            for row in conn.execute(
                text(
                    """
                    select
                        rt.id,
                        rt.raw_receipt_id,
                        rt.store_name,
                        rt.store_branch,
                        rt.purchase_at,
                        rt.total_amount,
                        rt.currency,
                        rt.parse_status,
                        rt.confidence_score,
                        rt.line_count,
                        rt.discount_total,
                        rt.created_at,
                        rr.original_filename,
                        rr.raw_status,
                        rr.imported_at
                    from receipt_tables rt
                    left join raw_receipts rr on rr.id = rt.raw_receipt_id
                    where rt.deleted_at is null
                    order by rt.created_at desc
                    limit :limit
                    """
                ),
                {"limit": max(1, min(int(limit or 200), 500))},
            ).mappings()
        ]

        line_stats = {
            str(row["receipt_table_id"]): _row_to_dict(row)
            for row in conn.execute(
                text(
                    """
                    select
                        receipt_table_id,
                        count(*) as line_count_actual,
                        round(coalesce(sum(coalesce(line_total, 0)), 0), 2) as line_sum,
                        round(coalesce(sum(coalesce(discount_amount, 0)), 0), 2) as discount_sum
                    from receipt_table_lines
                    group by receipt_table_id
                    """
                )
            ).mappings()
        }

    receipts = []
    for row in rows:
        receipt_id = str(row.get("id") or "")
        chain = _canonical_chain(str(row.get("store_name") or row.get("original_filename") or ""))
        if chain not in REQUIRED_CHAINS:
            continue
        receipts.append({
            **row,
            "chain": chain,
            "line_stats": line_stats.get(receipt_id, {}),
        })
    return receipts


def _receipt_ok(receipt: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    parse_status = str(receipt.get("parse_status") or "").strip().lower()
    if parse_status not in PASS_STATUSES:
        issues.append(f"status {parse_status or '-'}")
    if receipt.get("total_amount") in (None, ""):
        issues.append("totaalbedrag ontbreekt")
    if not receipt.get("purchase_at"):
        issues.append("datum/tijd ontbreekt")
    line_count_actual = int((receipt.get("line_stats") or {}).get("line_count_actual") or 0)
    if line_count_actual <= 0:
        issues.append("geen artikelregels")
    return not issues, issues


@router.post("/api/admin/kassa-regression/run")
def run_kassa_receipt_regression() -> dict[str, Any]:
    receipts = _load_kassa_receipts()
    by_chain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for receipt in receipts:
        by_chain[str(receipt.get("chain"))].append(receipt)

    chains: list[dict[str, Any]] = []
    all_passed = True

    for chain in REQUIRED_CHAINS.keys():
        chain_receipts = by_chain.get(chain, [])
        failures = []
        passed_count = 0
        for receipt in chain_receipts:
            ok, issues = _receipt_ok(receipt)
            if ok:
                passed_count += 1
            else:
                failures.append({
                    "receipt_id": receipt.get("id"),
                    "error": "; ".join(issues),
                    "details": {
                        "original_filename": receipt.get("original_filename"),
                        "store_name": receipt.get("store_name"),
                        "parse_status": receipt.get("parse_status"),
                        "total_amount": receipt.get("total_amount"),
                        "purchase_at": receipt.get("purchase_at"),
                        "line_count_actual": (receipt.get("line_stats") or {}).get("line_count_actual"),
                    },
                })
        missing = not chain_receipts
        status = "missing" if missing else ("failed" if failures else "passed")
        if status != "passed":
            all_passed = False
        chains.append({
            "chain": chain,
            "status": status,
            "receipt_count": len(chain_receipts),
            "passed_count": passed_count,
            "failed_count": len(failures),
            "failures": failures,
        })

    total_loaded = sum(item["receipt_count"] for item in chains)
    return {
        "test_type": "kassa_loaded_receipts_regression",
        "status": "passed" if all_passed else "failed",
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "required_chains": list(REQUIRED_CHAINS.keys()),
        "acceptance_basis": "Actuele door Kassa ingelezen bonnen in receipt_tables/receipt_table_lines, niet de oude raw parser-baseline.",
        "chains": chains,
        "summary": {
            "chain_count": len(chains),
            "loaded_receipt_count": total_loaded,
            "passed_chain_count": sum(1 for item in chains if item["status"] == "passed"),
            "failed_chain_count": sum(1 for item in chains if item["status"] == "failed"),
            "missing_chain_count": sum(1 for item in chains if item["status"] == "missing"),
        },
    }
