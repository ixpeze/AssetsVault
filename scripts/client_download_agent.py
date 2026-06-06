"""Local download agent for Obsidian Frost client PCs.

Run this on each teammate's PC. The web gallery talks to this localhost
service, so downloads are saved on the viewer's machine instead of the server.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from flask import Flask, jsonify, request

APP_NAME = "Obsidian Frost Client Downloader"
DEFAULT_PORT = 56789
CONFIG_ROOT = Path(os.environ.get("OBSIDIAN_AGENT_CONFIG_DIR") or os.environ.get("LOCALAPPDATA") or Path.home())
CONFIG_DIR = CONFIG_ROOT / "ObsidianFrostAgent"
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "ObsidianFrost"

log = logging.getLogger("client_download_agent")
app = Flask(__name__)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
executor: ThreadPoolExecutor | None = None
allowed_origins: set[str] | None = None


def _detect_file_extension(file_path: Path) -> str | None:
    try:
        with open(file_path, "rb") as file:
            header = file.read(8)
        if header.startswith(b"Rar!\x1a\x07\x01\x00") or header.startswith(b"Rar!\x1a\x07\x00"):
            return ".rar"
        if header.startswith(b"PK\x03\x04"):
            return ".zip"
        if header.startswith(b"7z\xbc\xaf\x27\x1c"):
            return ".7z"
    except Exception as exc:
        log.warning("Magic byte check failed for %s: %s", file_path, exc)
    return None


def _sanitize_filename(raw: str, max_length: int = 200) -> str:
    name = html.unescape(raw)
    name = unicodedata.normalize("NFKD", name)
    name = name.replace("\u2013", "-").replace("\u2014", "-")
    name = name.replace("\u2018", "'").replace("\u2019", "'")
    name = name.replace("\u201c", "").replace("\u201d", "")
    name = "".join(char for char in name if not unicodedata.combining(char))
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = re.sub(r"[^\w .\-]", "_", name, flags=re.ASCII)
    name = re.sub(r"[_\s]+", "_", name)
    name = name.strip("_. ")
    if len(name) > max_length:
        name = name[:max_length].rstrip("_. ")
    return name or "download"


def extract_id_from_url(url: str) -> str | None:
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None


def is_folder_url(url: str) -> bool:
    return "/folders/" in url or "drive/folders" in url


def get_folder_file_ids(url: str, session: requests.Session | None = None) -> list[str]:
    folder_id = extract_id_from_url(url)
    if not folder_id:
        return []
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
    try:
        resp = session.get(f"https://drive.google.com/drive/folders/{folder_id}", timeout=30)
        if resp.status_code != 200:
            return []
        file_ids = re.findall(r"/file/d/([a-zA-Z0-9_-]+)", resp.text)
        seen = set()
        unique_ids = []
        for file_id in file_ids:
            if file_id not in seen:
                seen.add(file_id)
                unique_ids.append(file_id)
        return [f"https://drive.google.com/file/d/{file_id}/view" for file_id in unique_ids]
    except Exception as exc:
        log.error("Failed to scrape folder file IDs: %s", exc)
        return []


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not read config: %s", exc)
    return {"download_dir": str(DEFAULT_DOWNLOAD_DIR)}


def _save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _get_download_dir() -> Path:
    config = _load_config()
    path = Path(config.get("download_dir") or DEFAULT_DOWNLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cors_origin(origin: str | None) -> str:
    if not origin:
        return "*"
    if allowed_origins is None or origin in allowed_origins:
        return origin
    return "null"


@app.after_request
def _add_cors_headers(resp):
    origin = request.headers.get("Origin")
    resp.headers["Access-Control-Allow-Origin"] = _cors_origin(origin)
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Max-Age"] = "86400"
    resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "download_dir": str(_get_download_dir()),
        "active_jobs": sum(1 for job in jobs.values() if job["status"] == "downloading"),
    })


@app.route("/settings", methods=["GET", "POST", "OPTIONS"])
def settings():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "GET":
        return jsonify(_load_config())

    data = request.get_json() or {}
    download_dir = str(data.get("download_dir") or "").strip()
    if not download_dir:
        return jsonify({"error": "download_dir is required"}), 400

    path = Path(download_dir).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return jsonify({"error": f"Could not create download directory: {exc}"}), 400

    config = _load_config()
    config["download_dir"] = str(path)
    _save_config(config)
    return jsonify({"message": "Settings saved", "download_dir": str(path)})


@app.route("/jobs", methods=["GET", "OPTIONS"])
def list_jobs():
    if request.method == "OPTIONS":
        return ("", 204)
    with jobs_lock:
        return jsonify(sorted(jobs.values(), key=lambda job: job["created_at"], reverse=True)[:50])


@app.route("/download", methods=["POST", "OPTIONS"])
def enqueue_download():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json() or {}
    url = str(data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    item_id = str(data.get("item_id") or "asset").strip()
    title = str(data.get("title") or f"asset_{item_id}").strip()
    target_urls = get_folder_file_ids(url) if is_folder_url(url) else [url]
    if not target_urls:
        return jsonify({"error": "No downloadable files found"}), 400

    created = []
    for index, target_url in enumerate(target_urls, start=1):
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "item_id": item_id,
            "title": title,
            "url": target_url,
            "status": "queued",
            "progress": 0,
            "bytes_written": 0,
            "total_bytes": 0,
            "speed_kbps": 0,
            "path": "",
            "error": "",
            "created_at": time.time(),
        }
        with jobs_lock:
            jobs[job_id] = job
        assert executor is not None
        executor.submit(_download_job, job_id, target_url, item_id, title, index, len(target_urls))
        created.append(job)

    return jsonify({
        "message": f"Queued {len(created)} download(s) on this PC",
        "jobs": created,
    })


def _initiate_gdrive_request(session: requests.Session, url: str, resume_from: int = 0):
    file_id = extract_id_from_url(url)
    if not file_id:
        raise ValueError(f"Could not extract Google Drive file ID from URL: {url}")

    headers = {}
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"

    response = session.get(
        "https://docs.google.com/uc",
        params={"export": "download", "id": file_id, "confirm": "t"},
        stream=True,
        allow_redirects=True,
        headers=headers,
        timeout=60,
    )

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type and not response.headers.get("Content-Disposition"):
        text = response.text
        action_match = re.search(r'action="([^"]+)"', text)
        if action_match:
            action_url = action_match.group(1).replace("&amp;", "&")
            inputs = re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', text)
            params = {key: value for key, value in inputs}
            response = session.get(
                action_url,
                params=params,
                stream=True,
                allow_redirects=True,
                headers=headers,
                timeout=60,
            )
    return response


def _filename_from_response(response: requests.Response, fallback: str) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r'filename="([^"]+)"', disposition) or re.search(r"filename=([^; ]+)", disposition)
    if match:
        return _sanitize_filename(match.group(1), max_length=220)
    return fallback


def _download_job(job_id: str, url: str, item_id: str, title: str, index: int, count: int) -> None:
    dest_dir = _get_download_dir()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    try:
        _update_job(job_id, status="downloading")
        response = _initiate_gdrive_request(session, url) if "drive.google.com" in url else session.get(
            url,
            stream=True,
            timeout=60,
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type and not response.headers.get("Content-Disposition"):
            preview = response.text[:200]
            raise RuntimeError(f"Remote server returned HTML instead of a file: {preview}")

        clean_title = _sanitize_filename(title)
        suffix = Path(url.split("?")[0]).suffix
        if not suffix or len(suffix) > 8 or not suffix.replace(".", "").isalnum():
            suffix = ".zip"
        base_name = f"{item_id}_{clean_title}"
        if count > 1:
            base_name = f"{base_name}_{index}"
        filename = _filename_from_response(response, f"{base_name}{suffix}")
        file_path = _unique_path(dest_dir / filename)
        part_path = file_path.with_name(f"{file_path.name}.part")

        total = int(response.headers.get("content-length", 0) or 0)
        written = 0
        started = time.time()
        last_update = 0.0
        with open(part_path, "wb") as file:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                file.write(chunk)
                written += len(chunk)
                now = time.time()
                if now - last_update >= 0.5:
                    last_update = now
                    elapsed = max(now - started, 0.001)
                    _update_job(
                        job_id,
                        bytes_written=written,
                        total_bytes=total,
                        progress=int(written / total * 100) if total else 0,
                        speed_kbps=round((written / 1024) / elapsed, 1),
                    )

        if file_path.exists():
            file_path.unlink()
        part_path.rename(file_path)

        detected_ext = _detect_file_extension(file_path)
        if detected_ext and detected_ext != file_path.suffix.lower():
            renamed = _unique_path(file_path.with_suffix(detected_ext))
            file_path.rename(renamed)
            file_path = renamed

        _update_job(
            job_id,
            status="completed",
            progress=100,
            bytes_written=written,
            total_bytes=total or written,
            path=str(file_path),
            speed_kbps=0,
        )
        log.info("Downloaded %s", file_path)
    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc), speed_kbps=0)
        log.error("Download failed: %s", exc)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _update_job(job_id: str, **updates) -> None:
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(updates)


def main() -> None:
    global executor, allowed_origins
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=int(os.environ.get("CLIENT_AGENT_PORT", DEFAULT_PORT)))
    parser.add_argument("--download-dir", default=os.environ.get("CLIENT_DOWNLOAD_DIR", ""))
    parser.add_argument("--workers", type=int, default=int(os.environ.get("CLIENT_AGENT_WORKERS", "2")))
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help="Allowed web origin. Repeat for multiple origins. Omit to allow any origin.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.download_dir:
        config = _load_config()
        config["download_dir"] = str(Path(args.download_dir).expanduser())
        _save_config(config)
    allowed_origins = set(args.allowed_origin) if args.allowed_origin else None
    executor = ThreadPoolExecutor(max_workers=max(1, args.workers))

    download_dir = _get_download_dir()
    print(f"{APP_NAME} running at http://127.0.0.1:{args.port}")
    print(f"Downloads will be saved to: {download_dir}")
    print("Keep this window open while using the gallery from this PC.")
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
