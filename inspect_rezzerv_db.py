import sqlite3

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

print("=== ALLE TABELLEN ===")
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cur.fetchall():
    print(row[0])

print("\n=== RECEIPT-ACHTIGE TABELLEN ===")
cur.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
  AND (
    name LIKE '%receipt%'
    OR name LIKE '%kassa%'
    OR name LIKE '%table%'
    OR name LIKE '%line%'
  )
ORDER BY name
""")
for row in cur.fetchall():
    print(row[0])

print("\n=== KOLOMMEN VAN receipt_tables ===")
try:
    cur.execute("PRAGMA table_info(receipt_tables)")
    cols = cur.fetchall()
    if cols:
        for col in cols:
            print(col)
    else:
        print("Tabel receipt_tables bestaat niet of heeft geen kolommen.")
except Exception as e:
    print(f"FOUT bij PRAGMA receipt_tables: {e}")

conn.close()
