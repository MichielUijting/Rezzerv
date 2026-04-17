import sqlite3
import json

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM receipt_sources LIMIT 20")
rows = [dict(r) for r in cur.fetchall()]
print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))

conn.close()
