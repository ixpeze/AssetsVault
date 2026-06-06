
import sqlite3
import os

db_path = '3dskyfree.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table_name, create_sql in tables:
    print(f"--- Table: {table_name} ---")
    print(create_sql)
    print("\n")

conn.close()
