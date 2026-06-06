"""
services.downloader — background download worker, queue manager, and LRU cache eviction.
"""
import os
import re
import time
import html
import logging
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import requests

from ..constants import BASE_DIR
from ..infrastructure.connection import get_db_fresh

log = logging.getLogger(__name__)

# Single instance lock, active downloader tracker, and pause registry
_lock = threading.Lock()
_active_downloads = {}  # item_id -> dict
_paused_jobs = set()    # set of job_ids requested to pause
_paused_lock = threading.Lock()


def get_active_download_progress(item_id: int) -> dict | None:
    """Read in-memory active download progress without hitting DB."""
    with _lock:
        return _active_downloads.get(item_id)


def get_all_active_downloads() -> list[dict]:
    """Read all in-memory active downloads."""
    with _lock:
        return list(_active_downloads.values())


# ── Thread-Safe Pause/Resume Job Registration ──

def pause_job(job_id: int):
    """Register a job as paused to trigger interruption in worker thread."""
    with _paused_lock:
        _paused_jobs.add(job_id)


def resume_job(job_id: int):
    """Remove a job from the paused registry."""
    with _paused_lock:
        _paused_jobs.discard(job_id)


def is_job_paused(job_id: int) -> bool:
    """Check if a job has been flagged as paused."""
    with _paused_lock:
        return job_id in _paused_jobs


# ── Google Drive Utility Helpers ──

def _detect_file_extension(file_path: Path) -> str | None:
    """Inspect the first few bytes of a file to definitively determine its archive format."""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(8)
            if header.startswith(b'Rar!\x1a\x07\x01\x00') or header.startswith(b'Rar!\x1a\x07\x00'):
                return '.rar'
            elif header.startswith(b'PK\x03\x04'):
                return '.zip'
            elif header.startswith(b'7z\xbc\xaf\x27\x1c'):
                return '.7z'
    except Exception as e:
        log.warning("[Downloader] Magic byte check failed for %s: %s", file_path, e)
    return None

def extract_id_from_url(url: str) -> str | None:
    """Extract file or folder ID from various Google Drive URL formats."""
    # File: /file/d/ID/view
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    # Folder: /drive/folders/ID or /folders/ID
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    # Open: ?id=ID
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None


def is_folder_url(url: str) -> bool:
    """Check if the URL points to a Google Drive folder."""
    return '/folders/' in url or 'drive/folders' in url


def get_folder_file_ids(url: str, session: requests.Session = None) -> list[str]:
    """
    Scrape a public Google Drive folder page to extract all child file IDs.
    Returns a list of direct download URLs.
    """
    folder_id = extract_id_from_url(url)
    if not folder_id:
        return []

    if session is None:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        resp = session.get(folder_url, timeout=30)
        if resp.status_code != 200:
            return []

        # Extract file IDs from the folder page HTML
        file_ids = re.findall(r'/file/d/([a-zA-Z0-9_-]+)', resp.text)
        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for fid in file_ids:
            if fid not in seen:
                seen.add(fid)
                unique_ids.append(fid)

        return [f"https://drive.google.com/file/d/{fid}/view" for fid in unique_ids]
    except Exception as e:
        log.error("[Downloader] Failed to scrape folder file IDs: %s", e)
        return []


def _sanitize_filename(raw: str, max_length: int = 200) -> str:
    """
    Produce a filesystem-safe filename from a potentially messy title.
    1. Decode HTML entities (&#8211; → –)
    2. Normalize Unicode to ASCII where possible (NFKD decomposition)
    3. Replace any non-alphanumeric/dot/hyphen/space with underscore
    4. Collapse whitespace and underscores
    5. Truncate to max_length to avoid OS path limits
    """
    # Decode HTML entities
    name = html.unescape(raw)
    # NFKD normalize: é → e, – → -, etc.
    name = unicodedata.normalize('NFKD', name)
    # Replace common Unicode dashes/quotes with ASCII equivalents
    name = name.replace('\u2013', '-').replace('\u2014', '-')  # en/em dash
    name = name.replace('\u2018', "'").replace('\u2019', "'")  # smart quotes
    name = name.replace('\u201c', '').replace('\u201d', '')     # double smart quotes
    # Strip combining characters (accents)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    # Replace filesystem-illegal and problematic characters
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    # Replace remaining non-ASCII with underscore
    name = re.sub(r'[^\w .\-]', '_', name, flags=re.ASCII)
    # Collapse runs of underscores/spaces into single underscore
    name = re.sub(r'[_\s]+', '_', name)
    # Strip leading/trailing separators
    name = name.strip('_. ')
    # Truncate
    if len(name) > max_length:
        name = name[:max_length].rstrip('_. ')
    return name or 'download'


def _resolve_download_directory(raw_path: str | None) -> Path:
    """Resolve configured download directory from project root if relative."""
    if not raw_path:
        return BASE_DIR / "data" / "downloads"
    path = Path(raw_path)
    return path if path.is_absolute() else BASE_DIR / path


def _portable_path(path: Path) -> str:
    """Store paths relative to the project root when possible."""
    absolute_path = path.resolve()
    try:
        return absolute_path.relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return str(absolute_path)


# ── Downloader Service Singleton ──

class DownloaderService:
    _instance = None
    _init_lock = threading.Lock()

    def __new__(cls):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super(DownloaderService, cls).__new__(cls)
                cls._instance.executor = ThreadPoolExecutor(max_workers=2)
                cls._instance.worker_thread = None
                cls._instance.running = False
            return cls._instance

    def start(self):
        """Start the background downloader loop."""
        with self._init_lock:
            if self.running:
                return
            self.running = True
            self.worker_thread = threading.Thread(target=self._queue_loop, daemon=True)
            self.worker_thread.start()
            log.info("[Downloader] Service started background queue loop.")

    def stop(self):
        """Stop the background downloader."""
        self.running = False
        self.executor.shutdown(wait=False)

    def _queue_loop(self):
        """Loop that polls database for pending download jobs."""
        while self.running:
            time.sleep(2)  # poll every 2 seconds
            conn = get_db_fresh()
            try:
                # Find a pending job
                job = conn.execute("""
                    SELECT id, item_id, url FROM download_jobs 
                    WHERE status = 'pending' 
                    ORDER BY id ASC LIMIT 1
                """).fetchone()

                if job:
                    job_id = job["id"]
                    item_id = job["item_id"]
                    url = job["url"]

                    # Discard pause flag if resuming
                    resume_job(job_id)

                    # Update job to running in DB
                    conn.execute(
                        "UPDATE download_jobs SET status = 'downloading' WHERE id = ?", 
                        (job_id,)
                    )
                    conn.commit()

                    # Start download task in thread pool
                    self.executor.submit(self._download_task, job_id, item_id, url)
            except Exception as e:
                log.error("[Downloader] Queue loop error: %s", e)
            finally:
                conn.close()

    def _download_task(self, job_id: int, item_id: int, url: str):
        """Execute the actual download with retry and pause handler in a worker thread."""
        log.info("[Downloader] Starting download task for item %d (job %d)", item_id, job_id)
        
        conn = get_db_fresh()
        try:
            # 1. Resolve configurations from settings table
            dest_dir_str = conn.execute(
                "SELECT value FROM settings WHERE key = 'download_directory'"
            ).fetchone()
            dest_dir = _resolve_download_directory(dest_dir_str["value"] if dest_dir_str else None)
            dest_dir.mkdir(parents=True, exist_ok=True)

            quota_str = conn.execute(
                "SELECT value FROM settings WHERE key = 'disk_quota'"
            ).fetchone()
            quota_gb = float(quota_str["value"]) if quota_str else 50.0  # Default 50GB

            collision_str = conn.execute(
                "SELECT value FROM settings WHERE key = 'collision_mode'"
            ).fetchone()
            collision_mode = collision_str["value"] if collision_str else "auto_rename"

            retry_count_str = conn.execute(
                "SELECT value FROM settings WHERE key = 'retry_count'"
            ).fetchone()
            max_retries = int(retry_count_str["value"]) if retry_count_str else 3

            # Fetch item details
            item = conn.execute("SELECT title, category_slug FROM items WHERE id = ?", (item_id,)).fetchone()
            if not item:
                raise ValueError(f"Item {item_id} not found in database.")

            # Sanitize filename using smart renaming standard
            clean_title = _sanitize_filename(item["title"])
            # Try to infer extension from url, default to .zip
            url_path = url.split("?")[0]
            ext = Path(url_path).suffix or ".zip"
            if len(ext) > 5 or not ext.replace('.', '').isalnum():
                ext = ".zip"
            filename = f"{item_id}_{clean_title}{ext}"
            file_path = dest_dir / filename
            part_path = dest_dir / f"{filename}.part"

            # 2. Check collision mode
            if file_path.exists():
                local_size = file_path.stat().st_size
                if collision_mode == "skip":
                    log.info("[Downloader] File already exists, skipping: %s", filename)
                    conn.execute("""
                        UPDATE download_jobs 
                        SET status = 'completed', progress = 100, bytes_written = ?, total_bytes = ?, finished_at = datetime('now') 
                        WHERE id = ?
                    """, (local_size, local_size, job_id))
                    conn.execute("UPDATE items SET local_file_path = ?, status = 'local' WHERE id = ?", (_portable_path(file_path), item_id))
                    conn.commit()
                    return
                elif collision_mode == "overwrite":
                    # Will check server size matching during streaming
                    pass
                else:  # auto_rename
                    # Rename the file path
                    base_name = file_path.stem
                    count = 1
                    while file_path.exists():
                        filename = f"{item_id}_{clean_title}_{count}{ext}"
                        file_path = dest_dir / filename
                        count += 1
                    part_path = dest_dir / f"{filename}.part"

            # 3. Check for existing partial file for resume
            resume_from = 0
            if part_path.exists():
                resume_from = part_path.stat().st_size
                log.info("[Downloader] Found existing .part file of size %d bytes. Resuming.", resume_from)

            # 4. Check quota before starting
            self._enforce_quota(dest_dir, quota_gb, conn)

            # 5. Perform download with exponential backoff retry loop
            skipped = False
            for attempt in range(max_retries + 1):
                try:
                    skipped, file_path = self._execute_stream(
                        job_id, item_id, url, file_path, part_path, resume_from, collision_mode
                    )
                    break  # Success
                except InterruptedError as ie:
                    # Paused mid-stream, bubble up immediately
                    raise ie
                except Exception as e:
                    if attempt < max_retries:
                        delay = 2 ** (attempt + 1)
                        log.warning("[Downloader] Attempt %d failed: %s. Retrying in %ds...", attempt + 1, e, delay)
                        conn.execute("UPDATE download_jobs SET error_message = ? WHERE id = ?", (f"Attempt {attempt + 1} failed. Retrying...", job_id))
                        conn.commit()
                        time.sleep(delay)
                        
                        # Double check pause flag
                        if is_job_paused(job_id):
                            raise InterruptedError("Download paused")
                    else:
                        raise e

            # 6. Save metadata back to items and complete job
            if not skipped:
                conn.execute(
                    "UPDATE items SET local_file_path = ?, status = 'local' WHERE id = ?", 
                    (_portable_path(file_path), item_id)
                )
                conn.execute("""
                    UPDATE download_jobs 
                    SET status = 'completed', progress = 100, error_message = NULL, finished_at = datetime('now') 
                    WHERE id = ?
                """, (job_id,))
                conn.commit()

                # Invalidate embedding cache if needed
                try:
                    from ..embedding_cache import invalidate
                    invalidate()
                except ImportError:
                    pass

                log.info("[Downloader] Download completed successfully for item %d. Saved to: %s", item_id, file_path)

        except InterruptedError:
            log.info("[Downloader] Download paused for item %d (job %d)", item_id, job_id)
            conn.execute("""
                UPDATE download_jobs 
                SET status = 'paused', error_message = 'Paused' 
                WHERE id = ?
            """, (job_id,))
            conn.execute("UPDATE items SET status = 'online' WHERE id = ?", (item_id,))
            conn.commit()

        except Exception as e:
            log.error("[Downloader] Download failed for item %d (job %d): %s", item_id, job_id, e)
            conn.execute("""
                UPDATE download_jobs 
                SET status = 'failed', error_message = ?, finished_at = datetime('now') 
                WHERE id = ?
            """, (str(e), job_id))
            conn.execute("UPDATE items SET status = 'online' WHERE id = ?", (item_id,))
            conn.commit()
        finally:
            conn.close()
            # Clean up active state and pause flags
            with _lock:
                if item_id in _active_downloads:
                    del _active_downloads[item_id]
            resume_job(job_id)

    def _initiate_gdrive_request(self, session: requests.Session, url: str, resume_from: int = 0, part_file: Path = None):
        """
        Make initial Google Drive request, handle virus scan interstitial.
        Ported from AssetForge's proven bypass logic.
        Returns the streaming response.
        """
        file_id = extract_id_from_url(url)
        if not file_id:
            raise ValueError(f"Could not extract Google Drive file ID from URL: {url}")

        EXPORT_URL = "https://docs.google.com/uc?export=download"
        headers = {}
        if resume_from > 0 and part_file and part_file.exists():
            headers['Range'] = f'bytes={resume_from}-'

        # Key fix: pass confirm=t upfront to bypass first-level virus scan
        response = session.get(
            EXPORT_URL, params={'id': file_id, 'confirm': 't'},
            stream=True, allow_redirects=True, headers=headers, timeout=60
        )

        # Handle virus scan interstitial page (second-level bypass)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type and not response.headers.get('Content-Disposition'):
            text = response.text
            # Parse form action URL from the interstitial page
            action_match = re.search(r'action="([^"]+)"', text)
            if action_match:
                action_url = action_match.group(1).replace('&amp;', '&')
                # Extract all hidden form inputs
                inputs = re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', text)
                params = {k: v for k, v in inputs}

                req_headers = {}
                if resume_from > 0:
                    req_headers['Range'] = f'bytes={resume_from}-'

                response = session.get(
                    action_url, params=params, stream=True,
                    allow_redirects=True, headers=req_headers, timeout=60
                )

        return response

    def _execute_stream(self, job_id: int, item_id: int, url: str, file_path: Path, part_path: Path, resume_from: int = 0, collision_mode: str = "auto_rename") -> tuple[bool, Path]:
        """Request streaming file download with GDrive redirection bypass, Range requests, and pause check."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        is_gdrive = "drive.google.com" in url
        response = None

        if is_gdrive:
            response = self._initiate_gdrive_request(session, url, resume_from, part_path)
        else:
            headers = {}
            if resume_from > 0:
                headers['Range'] = f'bytes={resume_from}-'
            response = session.get(url, stream=True, timeout=30, headers=headers)

        # Smart pre-download size-matching overwrite check
        if resume_from == 0 and collision_mode == "overwrite" and file_path.exists():
            server_size = int(response.headers.get('content-length', 0))
            local_size = file_path.stat().st_size
            if server_size > 0 and local_size == server_size:
                log.info("[Downloader] Local file size matches server content-length (%d). Skipping download.", local_size)
                response.close()
                
                # Update DB to completed immediately
                conn = get_db_fresh()
                try:
                    conn.execute("""
                        UPDATE download_jobs 
                        SET status = 'completed', progress = 100, bytes_written = ?, total_bytes = ?, finished_at = datetime('now') 
                        WHERE id = ?
                    """, (local_size, local_size, job_id))
                    conn.execute("UPDATE items SET local_file_path = ?, status = 'local' WHERE id = ?", (_portable_path(file_path), item_id))
                    conn.commit()
                finally:
                    conn.close()
                return True, file_path  # Skipped

        # Handle HTTP 416 Range Not Satisfiable — file may already be complete
        if response.status_code == 416:
            if part_path.exists():
                log.info("[Downloader] HTTP 416 — Range not satisfiable. File appears complete already.")
                if file_path.exists():
                    os.remove(file_path)
                os.rename(part_path, file_path)
                return False, file_path
            raise ConnectionError("HTTP 416 Range Not Satisfiable and no partial file found.")

        response.raise_for_status()

        # Critical validation: verify we got a binary file, not an HTML error page
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type and not response.headers.get('Content-Disposition'):
            # We still got an HTML page — the bypass failed
            body_preview = response.text[:500]
            response.close()
            raise ConnectionError(
                f"Google Drive returned an HTML page instead of the file. "
                f"The virus scan bypass may have failed. Preview: {body_preview[:200]}"
            )
        # Extract correct extension from Content-Disposition if present
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            match = re.search(r'filename="([^"]+)"', content_disposition)
            if not match:
                match = re.search(r'filename=([^; ]+)', content_disposition)
            if match:
                server_filename = match.group(1)
                server_ext = Path(server_filename).suffix.lower()
                if server_ext and server_ext != file_path.suffix.lower() and len(server_ext) <= 5 and server_ext.replace('.', '').isalnum():
                    log.info("[Downloader] Adjusting extension from %s to %s based on Content-Disposition", file_path.suffix, server_ext)
                    new_file_path = file_path.with_suffix(server_ext)
                    new_part_path = part_path.with_suffix(f"{server_ext}.part")
                    
                    # If we already had a part file, rename it to match new extension
                    if part_path.exists():
                        os.rename(part_path, new_part_path)
                    
                    file_path = new_file_path
                    part_path = new_part_path

        # Check if server responded with Partial Content
        is_partial = (response.status_code == 206)
        if not is_partial and resume_from > 0:
            log.warning("[Downloader] Server did not return HTTP 206 (Partial Content). Starting download from scratch.")
            resume_from = 0

        # Calculate total sizes
        server_content_len = int(response.headers.get('content-length', 0))
        total_size = server_content_len
        if is_partial:
            total_size += resume_from

        bytes_written = resume_from
        chunk_size = 1024 * 1024  # 1MB chunk size
        start_time = time.time()
        last_db_update = start_time

        # Setup initial active progress
        with _lock:
            _active_downloads[item_id] = {
                "item_id": item_id,
                "job_id": job_id,
                "progress": int((bytes_written / total_size * 100)) if total_size > 0 else 0,
                "bytes_written": bytes_written,
                "total_bytes": total_size,
                "speed_kbps": 0,
                "status": "downloading"
            }

        # Open `.part` file in append/write mode
        write_mode = "ab" if is_partial else "wb"
        try:
            with open(part_path, write_mode) as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    
                    # Check for pause event
                    if is_job_paused(job_id):
                        raise InterruptedError("Download paused")

                    f.write(chunk)
                    bytes_written += len(chunk)

                    # Speed and progress calculations
                    elapsed = time.time() - start_time
                    speed = ((bytes_written - resume_from) / 1024) / elapsed if elapsed > 0 else 0
                    progress = int((bytes_written / total_size * 100)) if total_size > 0 else 0

                    # Update in-memory tracker
                    with _lock:
                        if item_id in _active_downloads:
                            _active_downloads[item_id].update({
                                "progress": progress,
                                "bytes_written": bytes_written,
                                "total_bytes": total_size,
                                "speed_kbps": round(speed, 1)
                            })

                    # Throttle SQLite updates
                    current_time = time.time()
                    if current_time - last_db_update >= 1.0 or progress == 100:
                        last_db_update = current_time
                        conn = get_db_fresh()
                        try:
                            conn.execute("""
                                UPDATE download_jobs 
                                SET progress = ?, bytes_written = ?, total_bytes = ? 
                                WHERE id = ?
                            """, (progress, bytes_written, total_size, job_id))
                            conn.commit()
                        except Exception as db_err:
                            log.warning("[Downloader] Progress save database warning: %s", db_err)
                        finally:
                            conn.close()
        except InterruptedError as ie:
            # Save partial progress in DB before pausing
            conn = get_db_fresh()
            try:
                # Fallback calculations if not set
                prog = int((bytes_written / total_size * 100)) if total_size > 0 else 0
                conn.execute("""
                    UPDATE download_jobs 
                    SET progress = ?, bytes_written = ?, total_bytes = ? 
                    WHERE id = ?
                """, (prog, bytes_written, total_size, job_id))
                conn.commit()
            except Exception as db_err:
                log.warning("[Downloader] Progress save database warning on pause: %s", db_err)
            finally:
                conn.close()
            raise ie

        # Rename `.part` file to final destination path
        if part_path.exists():
            if file_path.exists():
                os.remove(file_path)
            os.rename(part_path, file_path)

        # ── Bulletproof Magic Byte Check ──
        if file_path.exists():
            true_ext = _detect_file_extension(file_path)
            if true_ext and true_ext != file_path.suffix.lower():
                log.info("[Downloader] Magic byte mismatch! Renaming %s to use %s extension", file_path.name, true_ext)
                new_file_path = file_path.with_suffix(true_ext)
                if new_file_path.exists():
                    os.remove(new_file_path)
                os.rename(file_path, new_file_path)
                file_path = new_file_path

        # Final write to database to ensure accurate total bytes and 100% progress
        conn = get_db_fresh()
        try:
            conn.execute("""
                UPDATE download_jobs 
                SET progress = 100, bytes_written = ?, total_bytes = ? 
                WHERE id = ?
            """, (bytes_written, total_size or bytes_written, job_id))
            conn.commit()
        except Exception as db_err:
            log.warning("[Downloader] Final progress save database warning: %s", db_err)
        finally:
            conn.close()

        return False, file_path  # Not skipped

    def _enforce_quota(self, dest_dir: Path, quota_gb: float, conn):
        """Enforce disk space quota by deleting oldest downloaded assets (LRU)."""
        quota_bytes = quota_gb * 1024 * 1024 * 1024
        
        # Calculate current total directory size
        total_size = sum(f.stat().st_size for f in dest_dir.glob('*') if f.is_file())
        
        if total_size <= quota_bytes:
            return

        log.info("[Downloader] Cache quota exceeded (current: %.2f GB, quota: %.2f GB). Evicting old files...", 
                 total_size / (1024**3), quota_gb)

        # Get list of files in directory with their last access/mod times
        files = []
        for file in dest_dir.glob('*'):
            if file.is_file():
                # Extract item_id from filename (e.g. 1234_Title.zip)
                parts = file.name.split('_')
                try:
                    item_id = int(parts[0])
                except ValueError:
                    item_id = None
                files.append({
                    "path": file,
                    "size": file.stat().st_size,
                    "mtime": file.stat().st_mtime,
                    "item_id": item_id
                })

        # Sort files by oldest mtime first (LRU behavior)
        files.sort(key=lambda x: x["mtime"])

        for f in files:
            if total_size <= quota_bytes * 0.90:  # free up until we are under 90% of quota
                break
            
            try:
                os.remove(f["path"])
                total_size -= f["size"]
                log.info("[Downloader] Evicted cache file: %s", f["path"].name)

                # Reset item status in database
                if f["item_id"]:
                    conn.execute(
                        "UPDATE items SET local_file_path = NULL, status = 'online' WHERE id = ?", 
                        (f["item_id"],)
                    )
            except Exception as e:
                log.error("[Downloader] Failed to delete file %s during eviction: %s", f["path"], e)
        
        conn.commit()


downloader_service = DownloaderService()
