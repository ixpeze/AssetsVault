#!/usr/bin/env python3
"""
Generate Semantic Embeddings
============================
Uses Ollama (nomic-embed-text) to create vector embeddings for items.
Enables semantic search ("cozy room" finding "warm lighting").

Embeddings are stored as float32 little-endian binary BLOBs
(768 × 4 = 3072 bytes each) rather than JSON text, reducing storage
by ~4.6× and eliminating json.loads on every similarity query.
"""

import sqlite3
import argparse
import sys
import time
import struct
import requests
from pathlib import Path

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

BASE_DIR = Path(__file__).parent.parent.parent  # project root
DB_PATH = BASE_DIR / "3dskyfree.db"
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"


def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _encode_embedding(vec) -> bytes:
    """Encode a list of floats as float32 LE binary."""
    if _NP:
        return np.array(vec, dtype=np.float32).tobytes()
    return struct.pack(f'<{len(vec)}f', *[float(x) for x in vec])


def _compute_norm(vec) -> float:
    if _NP:
        return float(np.linalg.norm(np.array(vec, dtype=np.float32)))
    return sum(x * x for x in vec) ** 0.5


def ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_embeddings (
            item_id   INTEGER PRIMARY KEY,
            embedding BLOB,
            norm      REAL,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )
    """)
    # Add norm column to existing DBs (safe no-op if already present)
    try:
        conn.execute("ALTER TABLE item_embeddings ADD COLUMN norm REAL")
        conn.commit()
    except Exception:
        pass


def check_ollama():
    """Verify Ollama is running and model is available."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check if model exists (handle tag suffix)
        if not any(EMBED_MODEL in m for m in models):
            print(f"❌ Model '{EMBED_MODEL}' not found. Available: {', '.join(models)}")
            print(f"   Pull it with: ollama pull {EMBED_MODEL}")
            return False
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {OLLAMA_URL}")
        print("   Start Ollama: ollama serve")
        return False


def get_embedding(text):
    """Get vector embedding for text."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": EMBED_MODEL,
                "prompt": text,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("embedding")
    except Exception as e:
        print(f"    ⚠️ Embedding error: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Generate semantic embeddings for items")
    parser.add_argument("--batch-size", type=int, default=100, help="Items to process per run")
    parser.add_argument("--reset", action="store_true", help="Clear existing embeddings")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print("❌ Database not found")
        return

    if not check_ollama():
        return

    conn = get_db()
    ensure_tables(conn)

    if args.reset:
        conn.execute("DELETE FROM item_embeddings")
        conn.commit()
        print("🗑️ Cleared item_embeddings table")

    # Get items without embeddings
    print("🔍 Finding unindexed items...")
    sql = """
        SELECT i.id, i.title, i.category_slug,
               GROUP_CONCAT(t.name, ', ') as tags
        FROM items i
        LEFT JOIN item_tags it ON i.id = it.item_id
        LEFT JOIN tags t ON it.tag_id = t.id
        WHERE i.id NOT IN (SELECT item_id FROM item_embeddings)
        GROUP BY i.id
    """
    if args.batch_size > 0:
        sql += f" LIMIT {args.batch_size}"

    items = conn.execute(sql).fetchall()
    total = len(items)
    
    if total == 0:
        print("✅ All items indexed!")
        conn.close()
        return

    print(f"📋 Processing {total} items...")
    
    processed = 0
    start_time = time.time()

    for i, item in enumerate(items):
        item_id = item["id"]
        title = item["title"] or ""
        category = item["category_slug"] or ""
        tags = item["tags"] or ""
        
        # Construct semantic text
        # "Title: Modern Sofa. Category: furniture. Tags: leather, black, living room"
        text = f"Title: {title}. Category: {category}. Tags: {tags}"
        
        embedding = get_embedding(text)
        
        if embedding:
            binary = _encode_embedding(embedding)
            norm   = _compute_norm(embedding)
            conn.execute("""
                INSERT INTO item_embeddings (item_id, embedding, norm)
                VALUES (?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET embedding = ?, norm = ?
            """, (item_id, binary, norm, binary, norm))
            conn.commit()
            processed += 1
            
        if (i+1) % 10 == 0:
            print(f"[{i+1}/{total}] Processed...", end="\r")

    elapsed = time.time() - start_time
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Processed: {processed} | Speed: {elapsed/max(1, processed):.2f}s/item")
    conn.close()

    conn.close()


def process_item(conn, item, tags=None, dry_run=False):
    """Process a single item: generate embedding from title + category + tags."""
    item_id = item["id"]
    title = item["title"] or ""
    category = item["category_slug"] or ""
    
    # If tags not provided, fetch them? 
    # For now assume orchestrator passes them, or we use what's in 'item' if 'tags' key exists
    if tags is None:
        if "tags" in item:
            tags = item["tags"] # could be string or list
        else:
            # Fetch tags
            rows = conn.execute("""
                SELECT t.name FROM item_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.item_id = ?
            """, (item_id,)).fetchall()
            tags = [r[0] for r in rows]

    if isinstance(tags, list):
        tags_str = ", ".join(tags)
    else:
        tags_str = str(tags) if tags else ""

    # Construct semantic text
    text = f"Title: {title}. Category: {category}. Tags: {tags_str}"
    
    embedding = get_embedding(text)
    
    if embedding:
        if not dry_run:
            binary = _encode_embedding(embedding)
            norm   = _compute_norm(embedding)
            conn.execute("""
                INSERT INTO item_embeddings (item_id, embedding, norm)
                VALUES (?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET embedding = ?, norm = ?
            """, (item_id, binary, norm, binary, norm))
            conn.commit()
        return embedding
    
    return None


if __name__ == "__main__":
    main()
