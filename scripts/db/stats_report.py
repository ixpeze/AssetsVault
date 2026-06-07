import sqlite3
import os
import json
import time
from pathlib import Path
import sys

# Add backend to path to import constants and helper functions
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.constants import DB_PATH, refresh_paid_slugs, PAID_CATEGORY_SLUGS

def get_stats():
    t_start = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Refresh paid slugs using db connection
        num_paid_slugs = refresh_paid_slugs(conn)
        print(f"Refreshed PAID_CATEGORY_SLUGS. Total paid slugs: {num_paid_slugs}")
        
        # We will compute stats based on:
        # 1. Categories total available (post_count)
        # 2. Items in DB (scraped)
        categories = conn.execute("SELECT slug, name, post_count FROM categories").fetchall()
        
        free_available = 0
        paid_available = 0
        
        for cat in categories:
            slug = cat["slug"]
            total = cat["post_count"] or 0
            if slug in PAID_CATEGORY_SLUGS:
                paid_available += total
            else:
                free_available += total
                
        results = {}
        for label, condition in [("Free Items", "is_paid = 0"), ("Paid Items", "is_paid = 1")]:
            print(f"\n--- Statistics for {label} ---")
            t0 = time.time()
            
            scraped_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition}").fetchone()[0]
            print(f"Query scraped_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            gdrive_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition} AND gdrive_link IS NOT NULL AND gdrive_link != ''").fetchone()[0]
            print(f"Query gdrive_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            mirror_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition} AND mirror_link IS NOT NULL AND mirror_link != ''").fetchone()[0]
            print(f"Query mirror_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            image_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition} AND ((image_url IS NOT NULL AND image_url != '') OR (local_image_path IS NOT NULL AND local_image_path != ''))").fetchone()[0]
            print(f"Query image_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            local_image_count = conn.execute(f"SELECT COUNT(*) FROM items WHERE {condition} AND local_image_path IS NOT NULL AND local_image_path != ''").fetchone()[0]
            print(f"Query local_image_count took {time.time() - t0:.3f}s")
            
            # Optimize: use EXISTS instead of joining/distinct in subqueries
            t0 = time.time()
            color_count = conn.execute(f"""
                SELECT COUNT(*) FROM items i
                WHERE i.{condition} AND EXISTS (
                    SELECT 1 FROM item_colors ic WHERE ic.item_id = i.id
                )
            """).fetchone()[0]
            print(f"Query color_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            embed_count = conn.execute(f"""
                SELECT COUNT(*) FROM items i
                WHERE i.{condition} AND EXISTS (
                    SELECT 1 FROM item_embeddings ie WHERE ie.item_id = i.id
                )
            """).fetchone()[0]
            print(f"Query embed_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            tag_count = conn.execute(f"""
                SELECT COUNT(*) FROM items i
                WHERE i.{condition} AND EXISTS (
                    SELECT 1 FROM item_tags it WHERE it.item_id = i.id
                )
            """).fetchone()[0]
            print(f"Query tag_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            downloaded_count = conn.execute(f"""
                SELECT COUNT(*) FROM items 
                WHERE {condition} AND (
                    (local_file_path IS NOT NULL AND local_file_path != '') OR
                    (local_path IS NOT NULL AND local_path != '')
                )
            """).fetchone()[0]
            print(f"Query downloaded_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            size_count = conn.execute(f"""
                SELECT COUNT(*) FROM items i
                JOIN item_metadata m ON i.id = m.item_id
                WHERE i.{condition} AND m.file_size IS NOT NULL AND m.file_size > 0
            """).fetchone()[0]
            print(f"Query size_count took {time.time() - t0:.3f}s")
            
            t0 = time.time()
            fully_enriched = conn.execute(f"""
                SELECT COUNT(*) FROM items i
                WHERE i.{condition}
                  AND EXISTS (SELECT 1 FROM item_tags it WHERE it.item_id = i.id)
                  AND EXISTS (SELECT 1 FROM item_colors ic WHERE ic.item_id = i.id)
                  AND EXISTS (SELECT 1 FROM item_embeddings ie WHERE ie.item_id = i.id)
            """).fetchone()[0]
            print(f"Query fully_enriched took {time.time() - t0:.3f}s")

            available = free_available if condition == "is_paid = 0" else paid_available

            results[condition] = {
                "available": available,
                "scraped": scraped_count,
                "gdrive": gdrive_count,
                "mirror": mirror_count,
                "image": image_count,
                "local_image": local_image_count,
                "color": color_count,
                "embed": embed_count,
                "tags": tag_count,
                "downloaded": downloaded_count,
                "size_info": size_count,
                "fully_enriched": fully_enriched
            }
            
            print(f"Total Available (from Category Post Counts): {available:,}")
            print(f"Total Scraped (Metadata in DB): {scraped_count:,} ({scraped_count/max(available, 1)*100:.2f}% of available)")
            print(f"  + Has GDrive Link: {gdrive_count:,} ({gdrive_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Mirror Link: {mirror_count:,} ({mirror_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Image: {image_count:,} ({image_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Local Image: {local_image_count:,} ({local_image_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Color: {color_count:,} ({color_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Embedded (embeddings): {embed_count:,} ({embed_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Tags: {tag_count:,} ({tag_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Size Info: {size_count:,} ({size_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Has Downloaded (local files): {downloaded_count:,} ({downloaded_count/max(scraped_count, 1)*100:.2f}% of scraped)")
            print(f"  + Fully Enriched: {fully_enriched:,} ({fully_enriched/max(scraped_count, 1)*100:.2f}% of scraped)")

        # Save JSON output for visualization script
        with open('scripts/db/stats_data.json', 'w') as f:
            json.dump(results, f, indent=4)
        print(f"\nStats data saved to scripts/db/stats_data.json. Entire run took {time.time() - t_start:.2f}s")

    finally:
        conn.close()

if __name__ == "__main__":
    get_stats()
