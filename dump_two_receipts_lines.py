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
            rt.id,
            rs.original_filename,
            rt.store_name,
            rt.purchase_at,
            rt.total_amount,
            rt.parse_status,
            rt.line_count
        FROM receipt_tables rt
        LEFT JOIN receipt_sources rs ON rs.raw_receipt_id = rt.raw_receipt_id
        WHERE rs.original_filename = ?
          AND rt.deleted_at IS NULL
        ORDER BY rt.created_at DESC
    """, (target,))
    receipt = cur.fetchone()

    if not receipt:
        print("GEEN actieve receipt gevonden")
        continue

    receipt_dict = dict(receipt)
    print(json.dumps(receipt_dict, indent=2, ensure_ascii=False, default=str))

    cur.execute("""
        SELECT *
        FROM receipt_table_lines
        WHERE receipt_table_id = ?
        ORDER BY
            CASE
                WHEN line_number IS NULL THEN 999999
                ELSE line_number
            END,
            created_at,
            id
    """, (receipt["id"],))
    rows = [dict(r) for r in cur.fetchall()]

    print(f"\n--- AANTAL LIJNEN: {len(rows)} ---")
    print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))

conn.close()
