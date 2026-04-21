import sqlite3
import json

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
SELECT
  id,
  raw_receipt_id,
  household_id,
  store_name,
  purchase_at,
  total_amount,
  parse_status,
  line_count,
  deleted_at,
  reference,
  notes,
  created_at,
  updated_at
FROM receipt_tables
WHERE deleted_at IS NOT NULL
ORDER BY deleted_at DESC, created_at DESC
""")

rows = [dict(r) for r in cur.fetchall()]
print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
conn.close()
