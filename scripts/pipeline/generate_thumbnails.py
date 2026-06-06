#!/usr/bin/env python3
"""Generate cached thumbnails for items with local preview images."""
import argparse
import os
import sqlite3
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.constants import DATA_DIR, THUMBNAILS_DIR  # noqa: E402

SIZES = (256, 512, 1024)


def _source_path(row: sqlite3.Row) -> Path | None:
    raw = row["local_image_path"]
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    category = row["category_slug"] or ""
    return DATA_DIR / category / path


def _thumb_path(item_id: int, size: int) -> Path:
    return Path(THUMBNAILS_DIR) / str(size) / f"{item_id}.jpg"


def _generate_one(item: dict, force: bool = False) -> dict:
    """Generate thumbnails for one item without touching SQLite."""
    item_id = item["id"]
    source = item["source_path"]
    if not source or not source.exists():
        return {"status": "missing", "records": []}

    existing = [_thumb_path(item_id, size).exists() for size in SIZES]
    if not force and all(existing):
        return {
            "status": "skipped",
            "records": [(item_id, size, str(_thumb_path(item_id, size))) for size in SIZES],
        }

    try:
        from PIL import Image
        from PIL import ImageFile

        ImageFile.LOAD_TRUNCATED_IMAGES = True

        records = []
        made_any = False
        with Image.open(source) as img:
            img.load()
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            elif img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg

            for size in SIZES:
                dest = _thumb_path(item_id, size)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and not force:
                    records.append((item_id, size, str(dest)))
                    continue

                thumb = img.copy()
                thumb.thumbnail((size, size), Image.LANCZOS)
                tmp = dest.with_suffix(f".{os.getpid()}.tmp")
                thumb.save(str(tmp), "JPEG", quality=85, optimize=True)
                tmp.replace(dest)
                records.append((item_id, size, str(dest)))
                made_any = True

        return {"status": "generated" if made_any else "skipped", "records": records}
    except Exception as exc:
        return {"status": "failed", "records": [], "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=min(8, max(1, (os.cpu_count() or 4) - 1)))
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    conn = sqlite3.connect(str(PROJECT_ROOT / "3dskyfree.db"), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        sql = """
            SELECT id, category_slug, local_image_path
            FROM items
            WHERE local_image_path IS NOT NULL
              AND local_image_path != ''
            ORDER BY id DESC
        """
        params = []
        if args.limit:
            sql += " LIMIT ?"
            params.append(args.limit)

        rows = conn.execute(sql, params).fetchall()
        items = [
            {"id": row["id"], "source_path": _source_path(row)}
            for row in rows
        ]

        total = generated = skipped = missing = failed = 0
        pending_records = []

        print(f"Starting thumbnail generation for {len(items)} items with {args.workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(_generate_one, item, args.force) for item in items]
            for future in as_completed(futures):
                total += 1
                result = future.result()
                status = result["status"]
                if status == "generated":
                    generated += 1
                elif status == "skipped":
                    skipped += 1
                elif status == "missing":
                    missing += 1
                else:
                    failed += 1

                pending_records.extend(result.get("records", []))
                if len(pending_records) >= args.batch_size:
                    conn.executemany(
                        "INSERT OR REPLACE INTO thumbnails (item_id, size, path) VALUES (?, ?, ?)",
                        pending_records,
                    )
                    conn.commit()
                    pending_records.clear()

                if total % 250 == 0:
                    print(
                        f"[{total}/{len(items)}] generated={generated} skipped={skipped} "
                        f"missing={missing} failed={failed}",
                        flush=True,
                    )

        if pending_records:
            conn.executemany(
                "INSERT OR REPLACE INTO thumbnails (item_id, size, path) VALUES (?, ?, ?)",
                pending_records,
            )
            conn.commit()

        print(
            f"Done. scanned={total} generated={generated} skipped={skipped} "
            f"missing={missing} failed={failed}",
            flush=True,
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
