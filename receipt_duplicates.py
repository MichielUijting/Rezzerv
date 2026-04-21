import sqlite3

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("""
SELECT
  COALESCE(store_name,'') as store_name,
  COALESCE(substr(purchase_at,1,16),'') as purchase_minute,
  COALESCE(total_amount,0) as total_amount,
  COUNT(*) as cnt
FROM receipt_tables
GROUP BY
  COALESCE(store_name,''),
  COALESCE(substr(purchase_at,1,16),''),
  COALESCE(total_amount,0)
HAVING COUNT(*) > 1
ORDER BY cnt DESC, purchase_minute DESC
""")

rows = cur.fetchall()
print("=== MOGELIJKE DUBBELEN ===")
for row in rows:
    print(row)

conn.close()
