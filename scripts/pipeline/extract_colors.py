#!/usr/bin/env python3
"""
Extract Dominant Colors
=======================
Analyzes preview images to find dominant colors for visual filtering.
Stores colors in 'item_colors' table as HSL + Hex.
"""

import sqlite3
import argparse
import sys
import time
from pathlib import Path
import colorsys
try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
except ImportError:
    print("❌ Pillow not found. Install it: pip install Pillow")
    sys.exit(1)

BASE_DIR = Path(__file__).parent.parent.parent  # project root
DB_PATH = BASE_DIR / "3dskyfree.db"
DATA_DIR = BASE_DIR / "data"

# colors.py lives in scripts/utils/ after the scripts reorganisation
sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from colors import COLOR_FAMILIES

def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_tables(conn):
    # Same as in gallery_app.py _ensure_visual_tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_colors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            h INTEGER,
            s INTEGER,
            l INTEGER,
            hex TEXT,
            percentage FLOAT,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_colors_item ON item_colors(item_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_colors_hsl ON item_colors(h, s, l)")


def rgb_to_hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(r, g, b)

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

# Pre-calculate palette RGBs
PALETTE_RGB = []
for fam in COLOR_FAMILIES:
    PALETTE_RGB.append({
        "hex": fam["hex"],
        "rgb": hex_to_rgb(fam["hex"]),
        "name": fam["name"]
    })

def get_closest_palette_color(rgb):
    """Find closest color in 48-color palette."""
    min_dist = float('inf')
    closest = None
    
    for p in PALETTE_RGB:
        # Euclidean distance
        d = sum((a-b)**2 for a, b in zip(rgb, p["rgb"])) # squared is enough for comparison
        if d < min_dist:
            min_dist = d
            closest = p
            
    return closest

def get_bg_color(img):
    """Estimate background color from corners."""
    # Sample 4 corners
    w, h = img.size
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((w-1, 0)),
        img.getpixel((0, h-1)),
        img.getpixel((w-1, h-1))
    ]
    # Find most common color in corners
    # (Simple majority)
    from collections import Counter
    c = Counter(corners)
    most_common, count = c.most_common(1)[0]
    return most_common

def color_dist(c1, c2):
    """Euclidean distance between two RGB tuples."""
    return sum((a-b)**2 for a, b in zip(c1, c2)) ** 0.5

def extract_colors(image_path, num_colors=5):
    """Extract dominant colors from an image, SNAP to fixed palette."""
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            # Resize for speed
            img.thumbnail((150, 150))
            
            # Detect background (approximate)
            bg_color = get_bg_color(img)
            
            # Quantize to N colors (ask for more to allow filtering)
            q_img = img.quantize(colors=num_colors+5, method=2)
            
            # getcolors() returns (count, index)
            palette = q_img.getpalette() # [r,g,b, r,g,b, ...]
            colors_count = q_img.getcolors(maxcolors=num_colors+6)
            
            if not colors_count:
                return []

            total_pixels = sum(c[0] for c in colors_count)
            
            # Temporary dict to aggregate into buckets
            # key: hex, value: percentage
            bucket_counts = {}
            
            # Sort by dominance
            sorted_colors = sorted(colors_count, key=lambda x: x[0], reverse=True)
            
            for count, index in sorted_colors:
                # Get RGB from palette
                r = palette[index*3]
                g = palette[index*3+1]
                b = palette[index*3+2]
                rgb = (r, g, b)
                
                # Filter Background
                if color_dist(rgb, bg_color) < 30:
                    continue
                
                # Snap to 48-color palette
                closest = get_closest_palette_color(rgb)
                if not closest: continue
                
                c_hex = closest["hex"]
                pct = count / total_pixels
                
                bucket_counts[c_hex] = bucket_counts.get(c_hex, 0) + pct
            
            # Convert aggregated buckets to result list
            results = []
            for hex_val, pct in bucket_counts.items():
                # We need HSL for DB (use the PALETTE's HSL, not original)
                r, g, b = hex_to_rgb(hex_val)
                h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
                
                results.append({
                    "h": int(h * 360),
                    "s": int(s * 100),
                    "l": int(l * 100),
                    "hex": hex_val,
                    "percentage": pct
                })
            
            # Sort by percentage descending
            results.sort(key=lambda x: x["percentage"], reverse=True)
            
            # Take top N keys (e.g. top 3-5 semantic families)
            return results[:num_colors]
            
    except Exception as e:
        print(f"    ⚠️ Error processing {image_path}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Extract dominant colors from 3D assets")
    parser.add_argument("--batch-size", type=int, default=100, help="Items to process per run")
    parser.add_argument("--reset", action="store_true", help="Clear existing colors")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Database not found")
        return

    conn = get_db()
    ensure_tables(conn)

    if args.reset:
        conn.execute("DELETE FROM item_colors")
        conn.commit()
        print("🗑️ Cleared item_colors table")

    # Get items that don't have colors
    # We check distinct item_id in item_colors
    print("🔍 Finding untagged items...")
    sql = """
        SELECT i.id, i.title, i.local_image_path, i.category_slug
        FROM items i
        WHERE i.local_image_path IS NOT NULL AND i.local_image_path != ''
        AND i.id NOT IN (SELECT DISTINCT item_id FROM item_colors)
    """
    if args.batch_size > 0:
        sql += f" LIMIT {args.batch_size}"

    items = conn.execute(sql).fetchall()
    total = len(items)
    
    if total == 0:
        print("✅ All items processed!")
        conn.close()
        return

    print(f"📋 Processing {total} items...")
    
    processed = 0
    start_time = time.time()

    for i, item in enumerate(items):
        item_id = item["id"]
        category_slug = item["category_slug"]
        rel_path = item["local_image_path"]
        
        # Resolve path
        if category_slug:
            img_path = DATA_DIR / category_slug / rel_path
        else:
            img_path = DATA_DIR / rel_path

        if not img_path.exists():
            print(f"    ⚠️ File missing: {rel_path}")
            continue

        colors = extract_colors(img_path)
        
        if colors:
            # Save to DB
            for c in colors:
                conn.execute("""
                    INSERT INTO item_colors (item_id, h, s, l, hex, percentage)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (item_id, c["h"], c["s"], c["l"], c["hex"], c["percentage"]))
            conn.commit()
            processed += 1
            
        if (i+1) % 10 == 0:
            print(f"[{i+1}/{total}] Processed...", end="\r")

    elapsed = time.time() - start_time
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Processed: {processed} | Speed: {elapsed/max(1, processed):.2f}s/item")
    conn.close()

    conn.close()


def process_item(conn, item, dry_run=False):
    """Process a single item: extract colors."""
    item_id = item["id"]
    category_slug = item["category_slug"] or ""
    rel_path = item["local_image_path"] or ""
    
    # Resolve path
    if category_slug:
        img_path = DATA_DIR / category_slug / rel_path
    else:
        img_path = DATA_DIR / rel_path

    if not img_path.exists():
        return None # File missing

    colors = extract_colors(img_path)
    
    if colors:
        if not dry_run:
            # Save to DB
            # First clear existing colors for this item? No, assuming untagged.
            # But if reprocessing, we might want to clear first.
            conn.execute("DELETE FROM item_colors WHERE item_id = ?", (item_id,))
            for c in colors:
                conn.execute("""
                    INSERT INTO item_colors (item_id, h, s, l, hex, percentage)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (item_id, c["h"], c["s"], c["l"], c["hex"], c["percentage"]))
            conn.commit()
        return colors
        
    return []


if __name__ == "__main__":
    main()
