import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "3dskyfree.db"
conn = sqlite3.connect(str(DB_PATH))

resolved = conn.execute("SELECT COUNT(*) FROM item_metadata WHERE file_size IS NOT NULL AND file_size > 0").fetchone()[0]
total_with_links = conn.execute("SELECT COUNT(*) FROM items WHERE (gdrive_link IS NOT NULL AND gdrive_link != '') OR (mirror_link IS NOT NULL AND mirror_link != '')").fetchone()[0]
total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
missing = total_with_links - resolved

print(f"Total items in DB:     {total_items:,}")
print(f"Items with links:      {total_with_links:,}")
print(f"Sizes resolved:        {resolved:,}")
print(f"Still missing:         {missing:,}")
print(f"Progress:              {resolved/total_with_links*100:.1f}%")
conn.close()
