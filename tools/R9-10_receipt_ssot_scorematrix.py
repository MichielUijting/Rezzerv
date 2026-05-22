from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = "http://localhost:8011"
DEFAULT_TOKEN = "rezzerv-dev-token::admin@rezzerv.local"
DEFAULT_HOUSEHOLD_ID = "1"
OUTPUT_DIR = Path("tools") / "reports"

CRITERIA_CODES = {
    "criterium_winkelnaam": "STORE_CHAIN_MISMATCH",
    "criterium_totaalbedrag": "TOTAL_AMOUNT_MISMATCH",
    "criterium_artikelcount": "ARTICLE_COUNT_MISMATCH",
    "criterium_regelsom": "LINE_SUM_TOTAL_MISMATCH",
}


def fetch_json(url: str, token: str) -> dict:
    request = Request(url)
    request.add_header("Authorization", f"Bearer {token}")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def criterion_ok(failed_criteria: list[str], mismatch_code: str) -> bool:
    return mismatch_code not in set(str(item) for item in failed_criteria or [])


def build_row(item: dict, detail: dict | None = None) -> dict:
    detail = detail or {}
    failed = item.get("po_norm_failed_criteria")
    if not isinstance(failed, list):
        failed = []
    merged = {**detail, **item}
    no_baseline = "NO_BASELINE_MATCH" in failed
    missing_active = "MISSING_ACTIVE_RECEIPT" in failed
    return {
        "receipt_table_id": merged.get("receipt_table_id") or merged.get("id"),
        "winkel": merged.get("store_name"),
        "winkelketen": merged.get("store_chain"),
        "bestand": merged.get("original_filename") or merged.get("source_file") or "",
        "status": merged.get("po_norm_status_label") or merged.get("inbox_status") or merged.get("status"),
        "criterium_winkelnaam": criterion_ok(failed, CRITERIA_CODES["criterium_winkelnaam"]),
        "criterium_totaalbedrag": criterion_ok(failed, CRITERIA_CODES["criterium_totaalbedrag"]),
        "criterium_artikelcount": criterion_ok(failed, CRITERIA_CODES["criterium_artikelcount"]),
        "criterium_regelsom": criterion_ok(failed, CRITERIA_CODES["criterium_regelsom"]),
        "geen_baseline_match": no_baseline,
        "ontbrekende_actieve_bon": missing_active,
        "failed_criteria": ";".join(str(code) for code in failed),
        "reden": merged.get("po_norm_reason") or merged.get("reason") or "",
        "totaalbedrag": merged.get("total_amount"),
        "artikelcount": merged.get("line_count"),
        "line_total_sum": merged.get("line_total_sum"),
        "discount_total_effective": merged.get("discount_total_effective"),
        "net_line_total_sum": merged.get("net_line_total_sum"),
        "created_at": merged.get("created_at"),
    }


def write_outputs(rows: list[dict], output_dir: Path = OUTPUT_DIR) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"R9-10_receipt_ssot_scorematrix_{timestamp}.csv"
    json_path = output_dir / f"R9-10_receipt_ssot_scorematrix_{timestamp}.json"
    fieldnames = [
        "receipt_table_id",
        "winkel",
        "winkelketen",
        "bestand",
        "status",
        "criterium_winkelnaam",
        "criterium_totaalbedrag",
        "criterium_artikelcount",
        "criterium_regelsom",
        "geen_baseline_match",
        "ontbrekende_actieve_bon",
        "failed_criteria",
        "reden",
        "totaalbedrag",
        "artikelcount",
        "line_total_sum",
        "discount_total_effective",
        "net_line_total_sum",
        "created_at",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    json_path.write_text(json.dumps({"items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def main() -> int:
    base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else BASE_URL
    token = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TOKEN
    household_id = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_HOUSEHOLD_ID

    receipts = fetch_json(f"{base_url}/api/receipts?householdId={quote(household_id)}", token)
    items = receipts.get("items") or []
    if not isinstance(items, list):
        raise SystemExit("R9-10 FAIL: /api/receipts bevat geen items[]")

    rows: list[dict] = []
    for item in items:
        receipt_id = str(item.get("receipt_table_id") or "").strip()
        detail = {}
        if receipt_id:
            try:
                detail = fetch_json(f"{base_url}/api/receipts/{quote(receipt_id)}", token)
            except Exception:
                detail = {}
        rows.append(build_row(item, detail))

    csv_path, json_path = write_outputs(rows)
    status_counts: dict[str, int] = {}
    failed_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1
        for code in str(row.get("failed_criteria") or "").split(";"):
            code = code.strip()
            if code:
                failed_counts[code] = failed_counts.get(code, 0) + 1

    print(f"R9-10 OK: {len(rows)} actieve kassabonnen verwerkt")
    print(f"R9-10 OK: status_counts={status_counts}")
    print(f"R9-10 OK: failed_criteria_counts={failed_counts}")
    print(f"R9-10 OK: CSV={csv_path}")
    print(f"R9-10 OK: JSON={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
