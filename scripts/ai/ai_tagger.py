#!/usr/bin/env python3
"""
AI-Powered Asset Tagger — Uses Ollama + LLaVA to generate visual tags
=====================================================================

Analyzes preview images of 3D assets and generates descriptive tags
like: modern, minimalist, wood, white, living room, sofa, etc.

Prerequisites:
    1. Install Ollama: https://ollama.com/download
    2. Pull a vision model: ollama pull llava-llama3

Usage:
    python ai_tagger.py                    # Tag all untagged items
    python ai_tagger.py --batch-size 50    # Process 50 items
    python ai_tagger.py --dry-run          # Preview without saving
    python ai_tagger.py --model llava      # Use a different model
"""

import argparse
import base64
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ 'requests' package required: pip install requests")
    sys.exit(1)

# ── Config ──
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "3dskyfree.db"
DATA_DIR = BASE_DIR / "data"
OLLAMA_URL = "http://localhost:11434"

PROMPT = """Analyze this 3D asset preview image. Generate 5-8 descriptive tags (visual only).
Focus on: Object type, Style, Material, Color, Room/Context.
Do NOT transcribe text or watermarks from the image.
Return ONLY a valid JSON array of lowercase strings.
Example: ["modern", "sofa", "leather", "gray", "living room"]"""




def get_db():
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)  # Increase timeout from 5s to 30s
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging for concurrency
    return conn


def retry_db(max_retries=5, base_delay=1.0):
    """Decorator to retry DB operations on lock errors."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "locked" in str(e) and attempt < max_retries - 1:
                        print(f"    ⏳ DB locked, retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay *= 1.5
                    else:
                        raise
        return wrapper
    return decorator


def ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            source TEXT DEFAULT 'auto'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item_tags (
            item_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (item_id, tag_id)
        )
    """)
    conn.commit()


@retry_db()
def get_untagged_items(conn, limit=None):
    """Get items that don't have AI-generated tags yet."""
    sql = """
        SELECT i.id, i.title, i.local_image_path, i.image_url, i.category_slug
        FROM items i
        WHERE i.id NOT IN (
            SELECT DISTINCT it.item_id FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
            WHERE t.source = 'ai'
        )
        AND (
            (i.local_image_path IS NOT NULL AND i.local_image_path != '')
            OR (i.image_url IS NOT NULL AND i.image_url != '')
        )
        ORDER BY (CASE WHEN i.local_image_path IS NOT NULL AND i.local_image_path != '' THEN 0 ELSE 1 END)
    """
    if limit:
        sql += f" LIMIT {limit}"
    return conn.execute(sql).fetchall()


# ... (image processing functions unchanged) ...


@retry_db()
def save_tags(conn, item_id, tags, source="ai"):
    """Save tags for an item."""
    for tag_name in tags:
        conn.execute(
            "INSERT OR IGNORE INTO tags (name, source) VALUES (?, ?)",
            (tag_name, source)
        )
        tag_row = conn.execute(
            "SELECT id FROM tags WHERE name = ?", (tag_name,)
        ).fetchone()
        if tag_row:
            conn.execute(
                "INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?)",
                (item_id, tag_row[0])
            )
    conn.commit()

try:
    from PIL import Image
    import io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _prepare_image_b64(raw_bytes):
    """Convert image bytes to JPEG base64 (LLaVA works best with JPEG).
    Resizes to max 768px on longest side to reduce memory usage."""
    if not raw_bytes:
        return None
    if HAS_PIL:
        try:
            img = Image.open(io.BytesIO(raw_bytes))
            # Resize if too large
            max_side = 768
            if max(img.size) > max_side:
                ratio = max_side / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            # Convert to RGB JPEG
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            pass
    # Fallback: send raw bytes
    return base64.b64encode(raw_bytes).decode("utf-8")


def encode_image_base64(image_path, category_slug=None):
    """Read a local image file, convert to JPEG base64.
    
    Path resolution: data/{category_slug}/{local_image_path}
    e.g. data/decor-helper-bathroom-toilet/images/23929.webp
    """
    if not image_path:
        return None
    if category_slug:
        full_path = DATA_DIR / category_slug / image_path
    else:
        full_path = DATA_DIR / image_path
    if not full_path.exists():
        return None
    with open(full_path, "rb") as f:
        return _prepare_image_b64(f.read())


def download_image_base64(image_url):
    """Download an image from URL and return JPEG base64."""
    try:
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        return _prepare_image_b64(resp.content)
    except Exception:
        return None


def query_ollama(model, image_b64):
    """Send image to Ollama vision model and get tags."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": PROMPT,
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 200,
                }
            },
            timeout=300,  # LLaVA cold start can be slow
        )
        resp.raise_for_status()
        result = resp.json()
        response_text = result.get("response", "")

        # Parse JSON array from response
        # Try to extract JSON array even if surrounded by text
        match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if match:
            try:
                tags = json.loads(match.group())
                # Normalize: lowercase, strip, max 2 words, skip empty
                tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()]
                tags = [t for t in tags if len(t) >= 2 and len(t.split()) <= 3]
                return tags[:10]
            except json.JSONDecodeError:
                pass # Fall through to fallback
        
        # Fallback: try parsing comma-separated lines
        # e.g. "modern, sofa, leather"
        if "," in response_text:
            tags = [t.strip().lower() for t in response_text.replace('\n', ',').split(',')]
            tags = [t for t in tags if len(t) >= 2 and len(t.split()) <= 3 and not any(c in t for c in "[]{}")]
            if len(tags) >= 3: # Only accept if we got a decent number of tags
                return tags[:10]

        print(f"    ⚠️ Could not parse tags from: {response_text[:100].replace(chr(10), ' ')}...")
        return []
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {OLLAMA_URL}")
        print("   Make sure Ollama is running: ollama serve")
        sys.exit(1)
    except Exception as e:
        print(f"    ⚠️ Ollama error: {e}")
        return []



def check_ollama(model):
    """Verify Ollama is running and model is available."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        # Check if model exists (handle tag suffix)
        model_names = [m.split(":")[0] for m in models]
        if model not in model_names and model not in models:
            print(f"❌ Model '{model}' not found. Available: {', '.join(models)}")
            print(f"   Pull it with: ollama pull {model}")
            return False
        print(f"✅ Ollama connected, using model: {model}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {OLLAMA_URL}")
        print("   Start Ollama: ollama serve")
        return False


def main():
    parser = argparse.ArgumentParser(description="AI-powered 3D asset tagger using Ollama")
    parser.add_argument("--model", default="moondream", help="Ollama vision model (default: moondream)")
    parser.add_argument("--batch-size", type=int, default=0, help="Max items to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    print(f"\n🤖 AI Asset Tagger")
    print(f"   Model: {args.model}")
    print(f"   Database: {DB_PATH}")
    print(f"   Dry run: {args.dry_run}\n")

    if not DB_PATH.exists():
        print("❌ Database not found")
        return

    if not check_ollama(args.model):
        return

    conn = get_db()
    ensure_tables(conn)

    items = get_untagged_items(conn, args.batch_size or None)
    total = len(items)
    print(f"📋 {total} items to tag\n")

    if total == 0:
        print("✅ All items already tagged!")
        conn.close()
        return

    tagged = 0
    failed = 0
    start_time = time.time()

    for i, item in enumerate(items):
        title = item["title"] or "Untitled"
        # Clean HTML entities
        title = title.replace("&#8211;", "-").replace("&amp;", "&")

        print(f"[{i+1}/{total}] {title[:60]}...", end=" ", flush=True)

        # Encode image — try local first, then URL fallback
        img_b64 = encode_image_base64(item["local_image_path"], item["category_slug"])
        if not img_b64 and item["image_url"]:
            img_b64 = download_image_base64(item["image_url"])
        if not img_b64:
            print("\n    ⚠️ No image (local or remote)")
            failed += 1
            continue

        # Query Ollama
        tags = query_ollama(args.model, img_b64)

        if tags:
            # Filter distinct tags to remove repetition
            unique_tags = list(dict.fromkeys(tags))
            print(f"→ {', '.join(unique_tags)}")
            if not args.dry_run:
                save_tags(conn, item["id"], unique_tags, source="ai")
            tagged += 1
        else:
            print("") # Newline handled by query_ollama's error print if any, otherwise force one
            failed += 1

        # Rate limiting
        time.sleep(0.1)

    elapsed = time.time() - start_time
    print(f"\n{'─' * 50}")
    print(f"✅ Done in {elapsed:.1f}s")
    print(f"   Tagged: {tagged} | Failed: {failed} | Total: {total}")
    if tagged > 0 and not args.dry_run:
        print(f"   Speed: {elapsed/tagged:.1f}s per item")
    print()

    conn.close()


def process_item(conn, item, model="moondream", dry_run=False):
    """Process a single item: tag it using AI."""
    title = item["title"] or "Untitled"
    # Clean HTML entities
    title = title.replace("&#8211;", "-").replace("&amp;", "&")

    # Encode image — try local first, then URL fallback
    img_b64 = encode_image_base64(item["local_image_path"], item["category_slug"])
    if not img_b64 and item["image_url"]:
        img_b64 = download_image_base64(item["image_url"])
    
    if not img_b64:
        return None  # Failed (no image)

    # Query Ollama
    tags = query_ollama(model, img_b64)

    if tags:
        # Filter distinct tags to remove repetition
        unique_tags = list(dict.fromkeys(tags))
        if not dry_run:
            save_tags(conn, item["id"], unique_tags, source="ai")
        return unique_tags
    
    return [] # Failed (no tags)


if __name__ == "__main__":
    main()
