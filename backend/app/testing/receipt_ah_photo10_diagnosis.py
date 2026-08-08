"""Diagnose-runner voor M2C2i-AH-Photo-04.

Doel: AH foto 10 isoleren zonder productiecode te wijzigen.

Deze runner:
- leest de huidige opgeslagen bonkop en bonregels uit;
- past financiële diagnose toe volgens discount-contract Variant B;
- voert een persistente reparse uit via de bestaande backendfunctie;
- leest de bon opnieuw uit;
- print before/after en classificeert de oorzaak voorlopig.

Geen parser-, OCR-, frontend-, database- of voorraadwijziging.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.services.receipt_service import reparse_receipt


ENGINE_URL = "sqlite:////app/data/rezzerv.db"
RECEIPT_STORAGE_ROOT = Path("/app/data/receipts")
AH_PHOTO_10_ID = "800894a1cf4a48598f4095be5532dc26"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class MoneySums:
    line_total_sum: Decimal
    line_discount_sum: Decimal
    receipt_discount_total: Decimal
    expected_total: Decimal | None

    @property
    def using_line_discount(self) -> Decimal:
        return (self.line_total_sum + self.line_discount_sum).quantize(CENT)

    @property
    def using_receipt_discount(self) -> Decimal:
        return (self.line_total_sum + self.receipt_discount_total).quantize(CENT)

    @property
    def using_both_discounts(self) -> Decimal:
        return (
            self.line_total_sum + self.line_discount_sum + self.receipt_discount_total
        ).quantize(CENT)

    def diff(self, value: Decimal) -> Decimal | None:
        if self.expected_total is None:
            return None
        return (value - self.expected_total).quantize(CENT)

    def closes_with_variant_b(self) -> bool:
        if self.expected_total is None:
            return False
        expected = self.expected_total.quantize(CENT)
        return self.using_line_discount == expected or self.using_receipt_discount == expected


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(CENT)


def maybe_money(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(CENT)


def table_columns(conn: Any, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
    return {row["name"] for row in rows}


def optional_select(alias: str, column: str, available: set[str]) -> str:
    if column in available:
        return f"{alias}.{column} AS {column}"
    return f"NULL AS {column}"


def fetch_snapshot(conn: Any, receipt_id: str) -> dict[str, Any] | None:
    rr_columns = table_columns(conn, "raw_receipts")

    source_type_select = optional_select("rr", "source_type", rr_columns)
    content_type_select = optional_select("rr", "content_type", rr_columns)
    storage_path_select = optional_select("rr", "storage_path", rr_columns)
    sha256_hash_select = optional_select("rr", "sha256_hash", rr_columns)

    query = f"""
        SELECT
            rt.id AS receipt_table_id,
            rt.raw_receipt_id,
            rr.original_filename,
            {source_type_select},
            {content_type_select},
            {storage_path_select},
            {sha256_hash_select},
            rt.store_name,
            rt.store_branch,
            rt.purchase_at,
            rt.total_amount,
            rt.discount_total,
            rt.currency,
            rt.parse_status,
            rt.confidence_score,
            rt.line_count,
            rt.updated_at
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        WHERE rt.id = :id OR rt.raw_receipt_id = :id
        LIMIT 1
    """

    row = conn.execute(text(query), {"id": receipt_id}).mappings().first()

    if not row:
        return None

    lines = conn.execute(
        text(
            """
            SELECT
                line_index,
                raw_label,
                normalized_label,
                quantity,
                unit,
                unit_price,
                line_total,
                discount_amount,
                article_match_status,
                confidence_score
            FROM receipt_table_lines
            WHERE receipt_table_id = :id
            ORDER BY line_index
            """
        ),
        {"id": row["receipt_table_id"]},
    ).mappings().all()

    line_total_sum = sum((money(line["line_total"]) for line in lines), Decimal("0.00"))
    line_discount_sum = sum(
        (money(line["discount_amount"]) for line in lines), Decimal("0.00")
    )

    sums = MoneySums(
        line_total_sum=line_total_sum.quantize(CENT),
        line_discount_sum=line_discount_sum.quantize(CENT),
        receipt_discount_total=money(row["discount_total"]),
        expected_total=maybe_money(row["total_amount"]),
    )

    return {"row": dict(row), "lines": [dict(line) for line in lines], "sums": sums}


def print_snapshot(label: str, snapshot: dict[str, Any] | None) -> None:
    print("")
    print(f"=== {label} ===")

    if snapshot is None:
        print("NOT_FOUND")
        return

    row = snapshot["row"]
    sums: MoneySums = snapshot["sums"]

    print("receipt_table_id       :", row["receipt_table_id"])
    print("raw_receipt_id         :", row["raw_receipt_id"])
    print("original_filename      :", row["original_filename"])
    print("source_type            :", row["source_type"])
    print("content_type           :", row["content_type"])
    print("storage_path           :", row["storage_path"])
    print("sha256_hash            :", row["sha256_hash"])
    print("store_name             :", row["store_name"])
    print("store_branch           :", row["store_branch"])
    print("purchase_at            :", row["purchase_at"])
    print("total_amount           :", row["total_amount"])
    print("discount_total         :", row["discount_total"])
    print("currency               :", row["currency"])
    print("parse_status           :", row["parse_status"])
    print("confidence_score       :", row["confidence_score"])
    print("line_count             :", row["line_count"])
    print("updated_at             :", row["updated_at"])
    print("stored_lines           :", len(snapshot["lines"]))
    print("line_total_sum         :", sums.line_total_sum)
    print("line_discount_sum      :", sums.line_discount_sum)
    print("receipt_discount_total :", sums.receipt_discount_total)
    print("expected_total         :", sums.expected_total)
    print("variant_b_line_total   :", sums.using_line_discount)
    print("variant_b_receipt_total:", sums.using_receipt_discount)
    print("unsafe_both_total      :", sums.using_both_discounts)
    print("diff_line_discount     :", sums.diff(sums.using_line_discount))
    print("diff_receipt_discount  :", sums.diff(sums.using_receipt_discount))
    print("diff_both_discounts    :", sums.diff(sums.using_both_discounts))
    print("variant_b_closes       :", sums.closes_with_variant_b())

    print("--- lines ---")
    for line in snapshot["lines"]:
        print(
            line["line_index"],
            "| raw=", line["raw_label"],
            "| norm=", line["normalized_label"],
            "| qty=", line["quantity"],
            "| unit=", line["unit"],
            "| unit_price=", line["unit_price"],
            "| line_total=", line["line_total"],
            "| discount=", line["discount_amount"],
            "| match=", line["article_match_status"],
        )


def classify(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    if after is None:
        return "DATA_NOT_FOUND"

    row = after["row"]
    sums: MoneySums = after["sums"]

    if row["parse_status"] == "approved" and sums.closes_with_variant_b():
        return "NO_FIX_NEEDED_AFTER_REPARSE"

    if not sums.closes_with_variant_b():
        before_lines = len(before["lines"]) if before else 0
        after_lines = len(after["lines"])
        if after_lines == 0:
            return "OCR_OR_SOURCE_EXTRACTION_EMPTY"
        if before_lines != after_lines:
            return "REPARSE_CHANGED_LINES_BUT_TOTAL_STILL_MISMATCH"
        return "LINE_SUM_TOTAL_MISMATCH_AFTER_REPARSE"

    if row["parse_status"] != "approved" and sums.closes_with_variant_b():
        return "STATUS_SSOT_OR_PAYLOAD_MISMATCH"

    return "UNKNOWN_REQUIRES_MANUAL_REVIEW"


def main() -> None:
    engine = create_engine(ENGINE_URL, future=True)

    with engine.begin() as conn:
        before = fetch_snapshot(conn, AH_PHOTO_10_ID)

    print_snapshot("BEFORE AH FOTO 10", before)

    if before is None:
        print("AH_PHOTO_10_DIAGNOSIS_READY")
        print("CAUSE_CATEGORY=DATA_NOT_FOUND")
        return

    print("")
    print("--- REPARSE AH FOTO 10 ---")
    result = reparse_receipt(engine, RECEIPT_STORAGE_ROOT, before["row"]["receipt_table_id"])
    print("reparse_result         :", result)

    with engine.begin() as conn:
        after = fetch_snapshot(conn, AH_PHOTO_10_ID)

    print_snapshot("AFTER AH FOTO 10", after)

    print("")
    print("=== CLASSIFICATION ===")
    print("AH_PHOTO_10_DIAGNOSIS_READY")
    print(f"CAUSE_CATEGORY={classify(before, after)}")


if __name__ == "__main__":
    main()
