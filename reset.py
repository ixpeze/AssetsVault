import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "3dskyfree.db"
DOWNLOADS_DIR = BASE_DIR / "data" / "downloads"


def _delete_download_files() -> int:
    """Delete files directly under the project-local downloads directory."""
    downloads_dir = DOWNLOADS_DIR.resolve()
    expected_parent = (BASE_DIR / "data").resolve()
    if not downloads_dir.is_relative_to(expected_parent):
        raise RuntimeError(f"Refusing to delete outside project data directory: {downloads_dir}")

    downloads_dir.mkdir(parents=True, exist_ok=True)

    deleted = 0
    for path in downloads_dir.iterdir():
        if not path.is_file():
            continue
        path.unlink()
        print(f"Deleted {path}")
        deleted += 1
    return deleted


def _reset_database() -> None:
    """Clear local download metadata and restore portable download settings."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("UPDATE items SET status = 'online', local_file_path = NULL WHERE status != 'online' OR local_file_path IS NOT NULL")
        conn.execute("DELETE FROM download_jobs")
        conn.execute("""
            INSERT INTO settings (key, value)
            VALUES ('download_directory', 'data/downloads')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    deleted = _delete_download_files()
    _reset_database()
    print(f"Deleted {deleted} downloaded file(s).")
    print("Reset download jobs, item local paths/statuses, and download_directory=data/downloads.")


if __name__ == "__main__":
    main()
