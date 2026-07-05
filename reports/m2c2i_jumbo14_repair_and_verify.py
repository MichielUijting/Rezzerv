"""M2C2i Jumbo foto 14 repair + verification runner.

Run in backend container:
  docker compose exec backend sh -lc 'cd /app && PYTHONPATH=/app python reports/m2c2i_jumbo14_repair_and_verify.py'

Purpose:
- repair the stored receipt_table for Jumbo foto 14 by invoking the existing
  production reparse path;
- verify that reparse/storage now contain 17 lines, total 38.80, line sum 38.80;
- verify that JUMBO ZALMSNIPPERS is present at 5.59;
- verify that JUMBO MAYO HALFVOL is stored at 1.25;
- leave Jumbo foto 12 untouched.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.receipt_service import reparse_receipt

RECEIPT_STORAGE_ROOT = Path("/app/data/receipts/raw")
OUTPUT_PATH = Path("reports/m2c2i_jumbo14_repair_and_verify.json")
TARGET_TOTAL = Decimal("38.80")
TARGET_HASH = "69c04e4b6a2a41acfa3fb0345d68601905367f1399098babc86498ad4f34cf08"


def dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def fetch_target() -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT rt.id AS receipt_table_id, rr.id AS raw_receipt_id,
                   rr.original_filename, rr.sha256_hash, rr.storage_path,
                   rt.store_name, rt.store_branch, rt.purchase_at,
                   rt.total_amount, rt.parse_status, rt.line_count
            FROM raw_receipts rr
            JOIN receipt_tables rt ON rt.raw_receipt_id = rr.id
            WHERE rr.deleted_at IS NULL
              AND rt.deleted_at IS NULL
              AND rr.sha256_hash = :sha256_hash
            ORDER BY rt.created_at DESC, rt.id DESC
            LIMIT 1
        """), {"sha256_hash": TARGET_HASH}).mappings().first()
    return dict(row) if row else None


def fetch_lines(receipt_table_id: str) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT line_index, raw_label, normalized_label, quantity, unit,
                   unit_price, line_total, discount_amount
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(is_deleted, 0) = 0
            ORDER BY line_index ASC
        """), {"receipt_table_id": receipt_table_id}).mappings().all()
    return [dict(row) for row in rows]


def summarize(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"exists": False}
    receipt_table_id = str(row.get("receipt_table_id") or "")
    lines = fetch_lines(receipt_table_id) if receipt_table_id else []
    line_sum = sum((dec(line.get("line_total")) for line in lines), Decimal("0.00")).quantize(Decimal("0.01"))
    zalm = [line for line in lines if "ZALMSNIPPERS" in str(line.get("raw_label") or line.get("normalized_label") or "").upper()]
    mayo = [line for line in lines if "MAYO HALFVOL" in str(line.get("raw_label") or line.get("normalized_label") or "").upper()]
    return {
        "exists": True,
        "receipt_table_id": receipt_table_id,
        "raw_receipt_id": row.get("raw_receipt_id"),
        "original_filename": row.get("original_filename"),
        "sha256_hash": row.get("sha256_hash"),
        "store_name": row.get("store_name"),
        "store_branch": row.get("store_branch"),
        "purchase_at": row.get("purchase_at"),
        "total_amount": float(dec(row.get("total_amount"))) if row.get("total_amount") is not None else None,
        "parse_status": row.get("parse_status"),
        "line_count": row.get("line_count"),
        "active_line_count": len(lines),
        "line_total_sum": float(line_sum),
        "zalmsnippers_lines": zalm,
        "mayo_halfvol_lines": mayo,
        "lines": lines,
    }


def assert_verified(summary: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not summary.get("exists"):
        return ["Jumbo foto 14 receipt not found by sha256_hash"]
    if dec(summary.get("total_amount")) != TARGET_TOTAL:
        failures.append(f"total_amount expected 38.80, got {summary.get('total_amount')}")
    if dec(summary.get("line_total_sum")) != TARGET_TOTAL:
        failures.append(f"line_total_sum expected 38.80, got {summary.get('line_total_sum')}")
    if int(summary.get("active_line_count") or 0) != 17:
        failures.append(f"active_line_count expected 17, got {summary.get('active_line_count')}")
    zalm_lines = summary.get("zalmsnippers_lines") or []
    if not any(dec(line.get("line_total")) == Decimal("5.59") for line in zalm_lines):
        failures.append("JUMBO ZALMSNIPPERS 5.59 missing")
    mayo_lines = summary.get("mayo_halfvol_lines") or []
    if not any(dec(line.get("line_total")) == Decimal("1.25") for line in mayo_lines):
        failures.append("JUMBO MAYO HALFVOL 1.25 missing")
    return failures


def main() -> int:
    before_row = fetch_target()
    before = summarize(before_row)
    if not before_row:
        report = {
            "name": "M2C2i Jumbo foto 14 repair + verification",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "before": before,
            "after": None,
            "failures": ["Target receipt not found"],
            "passed": False,
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print("M2C2i Jumbo 14 repair verifier FAILED: target not found")
        return 1

    receipt_table_id = str(before_row["receipt_table_id"])
    reparse_result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, receipt_table_id)
    after_row = fetch_target()
    after = summarize(after_row)
    failures = assert_verified(after)
    report = {
        "name": "M2C2i Jumbo foto 14 repair + verification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "receipt_table_id": receipt_table_id,
        "before": before,
        "reparse_result": reparse_result,
        "after": after,
        "failures": failures,
        "passed": not failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(json_safe(report), indent=2, ensure_ascii=False), encoding="utf-8")
    print("M2C2i Jumbo foto 14 repair + verification")
    print(f"Report: {OUTPUT_PATH}")
    print(f"Before: line_count={before.get('active_line_count')} sum={before.get('line_total_sum')} status={before.get('parse_status')}")
    print(f"After: line_count={after.get('active_line_count')} sum={after.get('line_total_sum')} status={after.get('parse_status')}")
    if failures:
        print("FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
