import sqlite3
import json

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
SELECT
  rt.id AS receipt_table_id,
  rt.raw_receipt_id,
  rt.store_name,
  rt.total_amount,
  rt.parse_status,
  rt.line_count,
  rr.*
FROM receipt_tables rt
LEFT JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
WHERE rt.deleted_at IS NULL
ORDER BY rt.created_at DESC
LIMIT 20
""")

rows = [dict(r) for r in cur.fetchall()]
print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))

conn.close()
