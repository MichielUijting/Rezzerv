import sqlite3
import json

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

targets = ["Aldi foto 2.jpg", "plus foto 1.jpg"]

for target in targets:
    print(f"\n===== RECEIPT: {target} =====")

    cur.execute("""
        SELECT
            rt.id AS receipt_table_id,
            rt.raw_receipt_id,
            rr.original_filename,
            rt.store_name,
            rt.purchase_at,
            rt.total_amount,
            rt.parse_status,
            rt.line_count
        FROM receipt_tables rt
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        WHERE rr.original_filename = ?
          AND rt.deleted_at IS NULL
        ORDER BY rt.created_at DESC
    """, (target,))
    receipt = cur.fetchone()

    if not receipt:
        print("GEEN actieve receipt gevonden")
        continue

    print(json.dumps(dict(receipt), indent=2, ensure_ascii=False, default=str))

    cur.execute("""
        SELECT
            id,
            receipt_table_id,
            line_index,
            raw_label,
            normalized_label,
            quantity,
            unit,
            unit_price,
            line_total,
            discount_amount,
            article_match_status,
            confidence_score,
            corrected_raw_label,
            corrected_quantity,
            corrected_unit,
            corrected_unit_price,
            corrected_line_total,
            is_deleted,
            is_validated
        FROM receipt_table_lines
        WHERE receipt_table_id = ?
        ORDER BY line_index, created_at, id
    """, (receipt["receipt_table_id"],))
    rows = [dict(r) for r in cur.fetchall()]

    print(f"\n--- AANTAL LIJNEN: {len(rows)} ---")
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))

conn.close()
