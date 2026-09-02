import os
import time
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from flask import Flask

# Override DB_PATH and other paths in constants and connection BEFORE initializing anything
import backend.constants
import backend.infrastructure.connection

if getattr(backend.constants, "DB_PATH", None) and Path(backend.constants.DB_PATH).parent.exists():
    temp_db_path = backend.constants.DB_PATH
    temp_downloads_dir = Path(backend.constants.DATA_DIR) / "downloads"
    temp_downloads_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = None
else:
    temp_dir = tempfile.TemporaryDirectory()
    temp_db_path = Path(temp_dir.name) / "test_3dskyfree.db"
    temp_downloads_dir = Path(temp_dir.name) / "downloads"
    temp_downloads_dir.mkdir(parents=True, exist_ok=True)
    backend.constants.DB_PATH = temp_db_path
    backend.constants.DATA_DIR = Path(temp_dir.name)
    backend.infrastructure.connection.DB_PATH = temp_db_path

from backend.infrastructure.connection import get_db_fresh, get_db, close_db

from backend.persistence.schema import init_schema
from backend.services.downloader import (
    DownloaderService, get_all_active_downloads, get_active_download_progress,
    pause_job, resume_job, is_folder_url, extract_id_from_url
)
from backend.routes.downloads import downloads_bp


class TestDownloaderAndSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_downloads_dir.mkdir(parents=True, exist_ok=True)
        conn = get_db_fresh()
        try:
            # Seed settings
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('download_directory', ?)",
                (str(temp_downloads_dir.absolute()),)
            )
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('disk_quota', '0.0001')")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('collision_mode', 'auto_rename')")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('retry_count', '3')")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('concurrency', '2')")
            
            # Seed downloader-specific test items
            conn.execute("""
                INSERT OR REPLACE INTO items (id, title, category_slug, gdrive_link, mirror_link)
                VALUES (901, 'Test Item 1', 'free-models', 'https://drive.google.com/uc?id=123', NULL)
            """)
            conn.execute("""
                INSERT OR REPLACE INTO items (id, title, category_slug, gdrive_link, mirror_link)
                VALUES (902, 'Test Item 2', 'free-models', NULL, 'https://example.com/file2.zip')
            """)
            conn.execute("""
                INSERT OR REPLACE INTO items (id, title, category_slug, gdrive_link, mirror_link)
                VALUES (903, 'Test Item 3', 'free-models', NULL, 'https://example.com/file3.zip')
            """)
            conn.commit()
        finally:
            conn.close()

        # Set up test Flask app for route testing
        cls.app = Flask(__name__)
        cls.app.register_blueprint(downloads_bp)
        cls.client = cls.app.test_client()

    def setUp(self):
        # Clear jobs and reset test item status
        conn = get_db_fresh()
        try:
            conn.execute("DELETE FROM download_jobs")
            conn.execute("UPDATE items SET local_file_path = NULL, status = 'online' WHERE id IN (901, 902, 903)")
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        conn = get_db_fresh()
        try:
            conn.execute("DELETE FROM download_jobs")
            conn.execute("DELETE FROM items WHERE id IN (901, 902, 903)")
            conn.commit()
        finally:
            conn.close()

    def test_schema_migration_columns(self):
        """Verify settings, download_jobs tables exist, and local_file_path / status columns were migrated."""
        conn = get_db_fresh()
        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t["name"] for t in tables]
            self.assertIn("settings", table_names)
            self.assertIn("download_jobs", table_names)
            
            cursor = conn.execute("PRAGMA table_info(items)")
            columns = [c["name"] for c in cursor.fetchall()]
            self.assertIn("local_file_path", columns)
            self.assertIn("status", columns)
        finally:
            conn.close()

    @patch("requests.Session.get")
    def test_downloader_gdrive_bypass_and_streaming(self, mock_get):
        """Verify the downloader requests and handles Google Drive bypass logic and throttles updates."""
        mock_confirm_html_response = MagicMock()
        mock_confirm_html_response.url = "https://docs.google.com/uc?export=download&id=123"
        mock_confirm_html_response.headers = {"Content-Type": "text/html", "content-type": "text/html"}
        mock_confirm_html_response.text = '''<html>
            <form id="download-form" action="/uc?export=download&confirm=t0k3n&id=123">
                <input type="hidden" name="id" value="123">
                <input type="hidden" name="confirm" value="t0k3n">
            </form>
        </html>'''
        
        mock_file_response = MagicMock()
        mock_file_response.url = "https://docs.google.com/uc?export=download&confirm=t0k3n&id=123"
        mock_file_response.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "100", "content-length": "100"
        }
        mock_file_response.iter_content.return_value = [b"A" * 50, b"B" * 50]
        mock_file_response.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_confirm_html_response, mock_file_response]

        # Enqueue download job
        conn = get_db_fresh()
        try:
            cursor = conn.execute(
                "INSERT INTO download_jobs (item_id, url, status) VALUES (901, 'https://drive.google.com/uc?id=123', 'pending')"
            )
            job_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        downloader = DownloaderService()
        downloader._download_task(job_id, 901, "https://drive.google.com/uc?id=123")

        # Verify DB updates
        conn = get_db_fresh()
        try:
            job = conn.execute("SELECT status, progress, bytes_written, total_bytes, error_message FROM download_jobs WHERE id = ?", (job_id,)).fetchone()
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["progress"], 100)
            self.assertEqual(job["bytes_written"], 100)
            self.assertEqual(job["total_bytes"], 100)
            self.assertIsNone(job["error_message"])

            item = conn.execute("SELECT local_file_path, status FROM items WHERE id = 901").fetchone()
            self.assertEqual(item["status"], "local")
            self.assertTrue(item["local_file_path"].endswith("901_Test_Item_1.zip"))
        finally:
            conn.close()

    @patch("requests.Session.get")
    def test_downloader_lru_eviction(self, mock_get):
        """Verify the downloader evicts older files when disk quota is exceeded."""
        # Clean downloads folder first
        for f in temp_downloads_dir.glob("*"):
            if f.is_file():
                f.unlink()

        # Quota is set to 0.0001 GB (~100KB)
        # Mock response 1 (120KB file, exceeding quota)
        mock_resp1 = MagicMock()
        mock_resp1.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "120000", "content-length": "120000"
        }
        mock_resp1.iter_content.return_value = [b"A" * 60000, b"B" * 60000]
        mock_resp1.raise_for_status = MagicMock()

        # Mock response 2 (60KB file)
        mock_resp2 = MagicMock()
        mock_resp2.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "60000", "content-length": "60000"
        }
        mock_resp2.iter_content.return_value = [b"C" * 30000, b"D" * 30000]
        mock_resp2.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_resp1, mock_resp2]

        downloader = DownloaderService()

        # Download first file
        downloader._download_task(101, 902, "https://example.com/file2.zip")
        time.sleep(0.1)

        # Download second file (triggers eviction of first file)
        downloader._download_task(102, 903, "https://example.com/file3.zip")

        # Verify eviction
        conn = get_db_fresh()
        try:
            item2 = conn.execute("SELECT local_file_path, status FROM items WHERE id = 902").fetchone()
            self.assertIsNone(item2["local_file_path"])
            self.assertEqual(item2["status"], "online")

            item3 = conn.execute("SELECT local_file_path, status FROM items WHERE id = 903").fetchone()
            self.assertIsNotNone(item3["local_file_path"])
            self.assertEqual(item3["status"], "local")

            self.assertFalse((temp_downloads_dir / "902_Test_Item_2.zip").exists())
            self.assertTrue((temp_downloads_dir / "903_Test_Item_3.zip").exists())
        finally:
            conn.close()

    @patch("requests.Session.get")
    def test_downloader_resume_range_request(self, mock_get):
        """Verify the downloader resumes a partial download (.part) using Range HTTP headers."""
        # Create a partial file manually (50 bytes)
        filename = "901_Test_Item_1.zip"
        part_file = temp_downloads_dir / f"{filename}.part"
        
        # Clean folder first
        for f in temp_downloads_dir.glob("*"):
            if f.is_file():
                f.unlink()

        with open(part_file, "wb") as f:
            f.write(b"A" * 50)

        # Mock the server to respond to the Range request
        mock_resp = MagicMock()
        mock_resp.status_code = 206  # Partial content
        mock_resp.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "50", "content-length": "50"
        }
        mock_resp.iter_content.return_value = [b"B" * 50]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Create download job in DB representing already 50 bytes written
        conn = get_db_fresh()
        try:
            cursor = conn.execute("""
                INSERT INTO download_jobs (item_id, url, status, progress, bytes_written, total_bytes)
                VALUES (901, 'https://example.com/file1.zip', 'pending', 50, 50, 100)
            """)
            job_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        downloader = DownloaderService()
        downloader._download_task(job_id, 901, "https://example.com/file1.zip")

        # Check Range header was passed correctly in requests.Session.get
        # The mock_get mock was called with headers={'Range': 'bytes=50-'}
        called_args, called_kwargs = mock_get.call_args
        self.assertIn("headers", called_kwargs)
        self.assertEqual(called_kwargs["headers"].get("Range"), "bytes=50-")

        # Verify combined file size and content
        final_file = temp_downloads_dir / filename
        self.assertTrue(final_file.exists())
        self.assertEqual(final_file.stat().st_size, 100)
        with open(final_file, "rb") as f:
            content = f.read()
            self.assertEqual(content, b"A" * 50 + b"B" * 50)

    @patch("requests.Session.get")
    def test_downloader_pause_mid_stream(self, mock_get):
        """Verify that marking a job as paused stops the stream loop mid-download and saves progress."""
        # Mock streaming response yielding chunk-by-chunk
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "100", "content-length": "100"
        }
        
        # When first chunk is read, we pause the job. When second is read, it shouldn't reach it because it pauses.
        def chunks(chunk_size):
            yield b"A" * 50
            # Trigger pause
            pause_job(job_id)
            yield b"B" * 50

        mock_resp.iter_content = chunks
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        # Create download job in DB
        conn = get_db_fresh()
        try:
            cursor = conn.execute("""
                INSERT INTO download_jobs (item_id, url, status)
                VALUES (901, 'https://example.com/file1.zip', 'pending')
            """)
            job_id = cursor.lastrowid
            conn.commit()
        finally:
            conn.close()

        downloader = DownloaderService()
        downloader._download_task(job_id, 901, "https://example.com/file1.zip")

        # Check job status is updated to paused
        conn = get_db_fresh()
        try:
            job = conn.execute("SELECT status, progress, bytes_written FROM download_jobs WHERE id = ?", (job_id,)).fetchone()
            self.assertEqual(job["status"], "paused")
            # Should have written 50 bytes and paused
            self.assertEqual(job["bytes_written"], 50)
            self.assertEqual(job["progress"], 50)

            # Check that `.part` file remains and is 50 bytes
            part_file = temp_downloads_dir / "901_Test_Item_1.zip.part"
            self.assertTrue(part_file.exists())
            self.assertEqual(part_file.stat().st_size, 50)
        finally:
            conn.close()

    @patch("backend.routes.downloads.get_folder_file_ids")
    def test_folder_expansion_enqueue(self, mock_get_folder_ids):
        """Verify that enqueuing a GDrive folder link automatically crawls and enqueues child file URLs."""
        # Mock get_folder_file_ids to return multiple file links
        mock_get_folder_ids.return_value = [
            "https://drive.google.com/file/d/child_abc/view",
            "https://drive.google.com/file/d/child_xyz/view"
        ]

        # Update items table to store a folder link
        conn = get_db_fresh()
        try:
            conn.execute("""
                UPDATE items 
                SET gdrive_link = 'https://drive.google.com/drive/folders/folder_123'
                WHERE id = 901
            """)
            conn.commit()
        finally:
            conn.close()

        # Request enqueue endpoint
        resp = self.client.post("/api/downloads/enqueue", json={"item_id": 901})
        self.assertEqual(resp.status_code, 200)
        res_data = resp.get_json()
        self.assertEqual(res_data["status"], "pending")
        self.assertEqual(len(res_data["job_ids"]), 2)

        # Verify that both jobs were created in DB
        conn = get_db_fresh()
        try:
            jobs = conn.execute("SELECT id, url, status FROM download_jobs WHERE item_id = 901").fetchall()
            self.assertEqual(len(jobs), 2)
            urls = [j["url"] for j in jobs]
            self.assertIn("https://drive.google.com/file/d/child_abc/view", urls)
            self.assertIn("https://drive.google.com/file/d/child_xyz/view", urls)
        finally:
            conn.close()

    def test_active_endpoint_includes_db_downloading_fallback(self):
        """Verify active endpoint keeps polling alive during DB-to-memory handoff."""
        conn = get_db_fresh()
        try:
            conn.execute("""
                INSERT INTO download_jobs
                    (item_id, url, status, progress, bytes_written, total_bytes)
                VALUES
                    (901, 'https://example.com/file1.zip', 'downloading', 25, 50, 200)
            """)
            conn.commit()
        finally:
            conn.close()

        resp = self.client.get("/api/downloads/active")
        self.assertEqual(resp.status_code, 200)
        active = resp.get_json()

        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["item_id"], 901)
        self.assertEqual(active[0]["status"], "downloading")
        self.assertEqual(active[0]["progress"], 25)
        self.assertEqual(active[0]["bytes_written"], 50)
        self.assertEqual(active[0]["total_bytes"], 200)

    @patch("requests.Session.get")
    def test_downloader_collision_modes(self, mock_get):
        """Verify collision resolution policies (skip, auto_rename, overwrite size-match)."""
        downloader = DownloaderService()

        # Seed the jobs in the database
        conn = get_db_fresh()
        try:
            conn.execute("INSERT INTO download_jobs (id, item_id, url, status) VALUES (201, 902, 'https://example.com/file2.zip', 'pending')")
            conn.execute("INSERT INTO download_jobs (id, item_id, url, status) VALUES (202, 902, 'https://example.com/file2.zip', 'pending')")
            conn.execute("INSERT INTO download_jobs (id, item_id, url, status) VALUES (203, 902, 'https://example.com/file2.zip', 'pending')")
            conn.commit()
        finally:
            conn.close()

        # 1. TEST SKIP MODE
        conn = get_db_fresh()
        try:
            conn.execute("UPDATE settings SET value = 'skip' WHERE key = 'collision_mode'")
            conn.commit()
        finally:
            conn.close()

        # Create existing file manually
        filename = "902_Test_Item_2.zip"
        file_path = temp_downloads_dir / filename
        if file_path.exists():
            file_path.unlink()
        with open(file_path, "wb") as f:
            f.write(b"Existing")

        # Run task
        downloader._download_task(201, 902, "https://example.com/file2.zip")

        # Verify that status was marked as completed and file was not modified
        conn = get_db_fresh()
        try:
            job = conn.execute("SELECT status, progress FROM download_jobs WHERE id = 201").fetchone()
            self.assertEqual(job["status"], "completed")
            self.assertEqual(file_path.stat().st_size, len("Existing"))
        finally:
            conn.close()

        # 2. TEST AUTO_RENAME MODE
        conn = get_db_fresh()
        try:
            conn.execute("UPDATE settings SET value = 'auto_rename' WHERE key = 'collision_mode'")
            conn.commit()
        finally:
            conn.close()

        # Mock download response
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "100", "content-length": "100"
        }
        mock_resp.iter_content.return_value = [b"A" * 100]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        downloader._download_task(202, 902, "https://example.com/file2.zip")

        # Should rename to suffix _1
        renamed_file = temp_downloads_dir / "902_Test_Item_2_1.zip"
        self.assertTrue(renamed_file.exists())
        self.assertEqual(renamed_file.stat().st_size, 100)

        # 3. TEST OVERWRITE SIZE MATCH
        conn = get_db_fresh()
        try:
            conn.execute("UPDATE settings SET value = 'overwrite' WHERE key = 'collision_mode'")
            conn.commit()
        finally:
            conn.close()

        # Prepare existing file of 100 bytes
        if renamed_file.exists():
            renamed_file.unlink()
        with open(file_path, "wb") as f:
            f.write(b"A" * 100)

        # Mock response returning size 100
        mock_resp_match = MagicMock()
        mock_resp_match.headers = {
            "Content-Type": "application/zip", "content-type": "application/zip",
            "Content-Length": "100", "content-length": "100"
        }
        mock_resp_match.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp_match

        # Run task
        downloader._download_task(203, 902, "https://example.com/file2.zip")

        # Verify skipped (no iter_content called on the response since size matches)
        mock_resp_match.iter_content.assert_not_called()
        conn = get_db_fresh()
        try:
            job = conn.execute("SELECT status, progress FROM download_jobs WHERE id = 203").fetchone()
            self.assertEqual(job["status"], "completed")
            self.assertEqual(file_path.stat().st_size, 100)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
