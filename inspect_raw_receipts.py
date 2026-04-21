import sqlite3

db = r"C:\Users\Gebruiker\Rezzerv-dev\backend\data\rezzerv.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("PRAGMA table_info(raw_receipts)")
for row in cur.fetchall():
    print(row)

conn.close()
