import sqlite3

def inspect():
    conn = sqlite3.connect('3dskyfree.db')
    cursor = conn.cursor()
    
    keywords = ['sofa', 'armchair', 'chair', 'wood', 'fabric', 'carpet', 'rug', 'textile', 'curtain']
    query = "SELECT slug, name, post_count FROM categories WHERE " + " OR ".join([f"slug LIKE '%{k}%'" for k in keywords]) + " ORDER BY slug"
    
    rows = cursor.execute(query).fetchall()
    
    print(f"Found {len(rows)} categories matching keywords:")
    for r in rows:
        print(f"{r[0]:<40} | {r[1]:<40} | {r[2]}")
        
    conn.close()

if __name__ == "__main__":
    inspect()
