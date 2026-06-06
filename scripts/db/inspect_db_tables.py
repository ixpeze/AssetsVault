
import sqlite3
import os

db_path = '3dskyfree.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all table names first
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print(f"Tables found: {tables}")

# Get schema for likely relevant tables
target_tables = ['categories', 'tags', 'item_categories', 'item_tags', 'items']
for table in target_tables:
    if table in tables:
        print(f"\n--- Schema for {table} ---")
        cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';")
        res = cursor.fetchone()
        if res:
            print(res[0])

conn.close()
