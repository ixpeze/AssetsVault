#!/usr/bin/env python3
"""
Local Recapture Worker & Direct Sync for 3DSkyFree
===================================================
Runs directly on your local machine to recapture missing download links.
Bypasses Cloudflare using Chrome TLS impersonation via curl_cffi and merges
recovered links directly into the local 3dskyfree.db database.

Automated Turnstile Solving:
Integrates with CapSolver and 2Captcha to automatically solve Cloudflare
Turnstile challenges for gated items.

Usage:
    python scripts/pipeline/run_local_worker.py --check-balance
    python scripts/pipeline/run_local_worker.py --slice-id 1 --limit 100
    python scripts/pipeline/run_local_worker.py --slice-id 1 --limit 50 --max-solves 10
    python scripts/pipeline/run_local_worker.py --help
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

# Force UTF-8 stdout/stderr on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

# Import modular Turnstile solver
from turnstile_solver import BaseTurnstileSolver, get_turnstile_solver, load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "3dskyfree.db"
TARGETS_FILE = BASE_DIR / "scripts" / "pipeline" / "recapture_targets.json.gz"
COOKIES_FILE = BASE_DIR / "cookies.json"

RE_GDRIVE = re.compile(r'href=["\']?(https?://drive\.google\.com/[^"\'<>\s]+)', re.IGNORECASE)
RE_MIRROR = re.compile(r'href=["\']?(https?://download\.3dskyfree\.com/[^"\'<>\s]+)', re.IGNORECASE)

DEFAULT_SITEKEY = "0x4AAAAAADYMJ4ffYfMnBIwc"
AJAX_URL = "https://3dskyfree.com/wp-admin/admin-ajax.php"

db_lock = threading.Lock()


class SolveBudgetTracker:
    """Thread-safe counter to enforce max Turnstile solves per run."""
    def __init__(self, max_solves: int):
        self.max_solves = max_solves
        self.count = 0
        self.lock = threading.Lock()

    def can_solve(self) -> bool:
        if self.max_solves <= 0:
            return True
        with self.lock:
            return self.count < self.max_solves

    def record_solve(self) -> int:
        with self.lock:
            self.count += 1
            return self.count


def extract_links(html: str) -> tuple[Optional[str], Optional[str]]:
    if not html:
        return None, None
    gdrive, mirror = None, None
    match_g = RE_GDRIVE.search(html)
    if match_g:
        gdrive = re.sub(r'/view\?usp=drivesdk.*', '/view', unquote(match_g.group(1)))
    match_m = RE_MIRROR.search(html)
    if match_m:
        mirror = unquote(match_m.group(1))
    return gdrive, mirror


def extract_gate_info(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract post_id and nonce from dts-gate attributes."""
    if "dts-gate" not in html:
        return None, None
    match_id = re.search(r'data-post-id=["\'](\d+)["\']', html)
    match_nonce = re.search(r'data-nonce=["\']([^"\']+)["\']', html)
    post_id = match_id.group(1) if match_id else None
    nonce = match_nonce.group(1) if match_nonce else None
    return post_id, nonce


def load_session() -> requests.Session:
    if USE_CURL_CFFI:
        session = requests.Session(impersonate="chrome124")
    else:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    if COOKIES_FILE.exists():
        try:
            raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            cookies = {}
            if isinstance(raw, list):
                cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
            elif isinstance(raw, dict):
                cookies = {str(k): str(v) for k, v in raw.items()}
            for k, v in cookies.items():
                session.cookies.set(k, v, domain="3dskyfree.com")
        except Exception:
            pass

    return session


def ensure_checkpoint_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recapture_checkpoints (
            run_id       TEXT NOT NULL,
            item_id      INTEGER NOT NULL,
            completed_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (run_id, item_id)
        )
    """)
    conn.commit()


def unlock_turnstile_gate(
    session: requests.Session,
    item_url: str,
    post_id: str,
    nonce: Optional[str],
    solver: BaseTurnstileSolver
) -> tuple[Optional[str], Optional[str], str]:
    """Request a Turnstile token via solver and post to WordPress unlock AJAX."""
    try:
        token = solver.solve(url=item_url, sitekey=DEFAULT_SITEKEY, action="view-post")
        if not token:
            return None, None, "solver_empty_token"

        # If nonce was missing from tag, request fresh nonce
        if not nonce:
            try:
                r_n = session.post(AJAX_URL, data={"action": "dts_fresh_nonce", "post_id": post_id}, timeout=15)
                n_json = r_n.json()
                if n_json.get("success") and n_json.get("data", {}).get("nonce"):
                    nonce = n_json["data"]["nonce"]
            except Exception:
                pass

        resp = session.post(
            AJAX_URL,
            data={
                "action": "dts_unlock_content",
                "post_id": post_id,
                "token": token,
                "nonce": nonce or ""
            },
            headers={
                "Referer": item_url,
                "X-Requested-With": "XMLHttpRequest"
            },
            timeout=20
        )
        data = resp.json()
        if data.get("success") and "html" in data.get("data", {}):
            unlocked_html = data["data"]["html"]
            gdrive, mirror = extract_links(unlocked_html)
            if gdrive or mirror:
                return gdrive, mirror, "unlocked"
            return None, None, "unlocked_no_link"
        else:
            msg = data.get("data", {}).get("message") or "unlock_failed"
            return None, None, f"unlock_fail: {msg}"
    except Exception as e:
        return None, None, f"solver_error: {e}"


def process_item(
    item: dict,
    session: requests.Session,
    delay: float,
    solver: Optional[BaseTurnstileSolver] = None,
    budget: Optional[SolveBudgetTracker] = None
) -> tuple[int, Optional[str], Optional[str], str]:
    item_id = item["id"]
    url = item["url"]

    if delay > 0:
        time.sleep(delay)

    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 200:
            # 1. Direct link check
            gdrive, mirror = extract_links(resp.text)
            if gdrive or mirror:
                return item_id, gdrive, mirror, "found"

            # 2. Check if gated by Turnstile
            post_id, nonce = extract_gate_info(resp.text)
            if post_id:
                if solver and budget and budget.can_solve():
                    solve_num = budget.record_solve()
                    gdrive, mirror, status = unlock_turnstile_gate(session, url, post_id, nonce, solver)
                    return item_id, gdrive, mirror, f"{status} (solve #{solve_num})"
                elif solver and budget and not budget.can_solve():
                    return item_id, None, None, "budget_limit"
                else:
                    return item_id, None, None, "gated_no_solver"

            # 3. Fallbacks
            if "restricted to paid" in resp.text.lower() or "members <br> only" in resp.text.lower():
                return item_id, None, None, "restricted"
            else:
                return item_id, None, None, "no_link"
        elif resp.status_code == 404:
            return item_id, None, None, "404"
        else:
            return item_id, None, None, f"http_{resp.status_code}"
    except Exception as e:
        return item_id, None, None, f"error: {e}"


def run_worker(
    slice_id: int,
    num_slices: int = 10,
    limit: int = 500,
    delay: float = 0.2,
    num_workers: int = 3,
    solver_provider: Optional[str] = None,
    api_key: Optional[str] = None,
    max_solves: int = 0
):
    if not TARGETS_FILE.exists():
        print(f"❌ Targets manifest not found at {TARGETS_FILE}")
        return

    with gzip.open(TARGETS_FILE, "rt", encoding="utf-8") as f:
        targets_data = json.load(f)

    all_items = targets_data.get("items", [])
    slice_items = [it for it in all_items if it["id"] % num_slices == slice_id]

    conn = sqlite3.connect(str(DB_PATH), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_checkpoint_table(conn)

    existing = conn.execute("SELECT id FROM items WHERE (gdrive_link IS NOT NULL AND gdrive_link != '') OR (mirror_link IS NOT NULL AND mirror_link != '')").fetchall()
    already_has_link = {r[0] for r in existing}

    checked_rows = conn.execute("SELECT item_id FROM recapture_checkpoints").fetchall()
    already_checked = {r[0] for r in checked_rows}

    pending = [it for it in slice_items if it["id"] not in already_has_link and it["id"] not in already_checked]
    if limit > 0:
        pending = pending[:limit]

    # Initialize Turnstile solver if available
    solver = None
    if solver_provider != "none":
        solver = get_turnstile_solver(provider=solver_provider, api_key=api_key)

    budget = SolveBudgetTracker(max_solves)

    print("=" * 68)
    print(f"💻 Local Auxiliary Worker — Slice {slice_id}/{num_slices}")
    print(f"   Target Items in Slice: {len(slice_items):,}")
    print(f"   Items to Process:      {len(pending):,} (limit: {limit})")
    print(f"   Concurrent Workers:    {num_workers} threads | Delay: {delay}s")
    if solver:
        print(f"   Turnstile Solver:      {solver.name} (Max budget: {max_solves if max_solves > 0 else 'Unlimited'} solves)")
    else:
        print("   Turnstile Solver:      None (gated items will be logged as 'gated_no_solver')")
    if USE_CURL_CFFI:
        print("   TLS Engine:            curl_cffi (Chrome 124 TLS impersonation)")
    print("=" * 68)

    if not pending:
        print("✨ All items in this slice have already been processed!")
        conn.close()
        return

    found_count = 0
    unlocked_count = 0
    gated_count = 0
    processed_count = 0
    start_time = time.time()

    thread_sessions = {}

    def get_thread_session():
        tid = threading.get_ident()
        if tid not in thread_sessions:
            thread_sessions[tid] = load_session()
        return thread_sessions[tid]

    def worker_task(item):
        session = get_thread_session()
        return process_item(item, session, delay, solver=solver, budget=budget)

    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_item = {executor.submit(worker_task, it): it for it in pending}

            for future in as_completed(future_to_item):
                processed_count += 1
                item_id, gdrive, mirror, status = future.result()

                with db_lock:
                    if "unlocked" in status or status == "found":
                        if "unlocked" in status:
                            unlocked_count += 1
                        else:
                            found_count += 1

                        conn.execute("""
                            UPDATE items
                            SET gdrive_link = COALESCE(?, gdrive_link),
                                mirror_link = COALESCE(?, mirror_link)
                            WHERE id = ?
                        """, (gdrive, mirror, item_id))
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ✅ LINK ({status}): {gdrive or mirror}")
                    elif "gated" in status:
                        gated_count += 1
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} 🛡️ {status}")
                    elif status == "restricted":
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} 🔒 Restricted (paid)")
                    elif status == "no_link":
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ℹ No link on page")
                    else:
                        print(f"[{processed_count}/{len(pending)}] ID:{item_id} ⚠️ {status}")

                    # Mark checkpoint
                    conn.execute("""
                        INSERT OR REPLACE INTO recapture_checkpoints (run_id, item_id, completed_at)
                        VALUES ('local_worker', ?, datetime('now'))
                    """, (item_id,))

                    if processed_count % 15 == 0:
                        conn.commit()

        conn.commit()
    finally:
        conn.close()

    duration = time.time() - start_time
    rate = (processed_count / max(1.0, duration))
    print("\n" + "=" * 68)
    print(f"🎉 Slice {slice_id} Finished in {duration:.1f}s ({rate:.1f} items/sec)")
    print(f"   • Items Processed:      {processed_count}")
    print(f"   • Direct Links Saved:   {found_count}")
    print(f"   • Solved/Unlocked:      {unlocked_count}")
    print(f"   • Gated (Unsolved):     {gated_count}")
    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="Local Recapture Worker with Turnstile Solver for 3DSkyFree")
    parser.add_argument("--slice-id", type=str, default="1", help="Slice ID (0-9 or 'all', default: 1)")
    parser.add_argument("--num-slices", type=int, default=10, help="Total number of slices (default: 10)")
    parser.add_argument("--limit", type=int, default=100, help="Max items to process per slice (default: 100)")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between requests in seconds (default: 0.2)")
    parser.add_argument("--workers", type=int, default=3, help="Number of concurrent worker threads (default: 3)")
    parser.add_argument("--solver", type=str, default=None, choices=["capsolver", "2captcha", "none", None], help="Solver provider (default: auto from .env)")
    parser.add_argument("--api-key", type=str, default=None, help="Solver API key (overrides .env)")
    parser.add_argument("--max-solves", type=int, default=0, help="Max Turnstile solves for this run (0 = unlimited, default: 0)")
    parser.add_argument("--check-balance", action="store_true", help="Check solver balance and exit")

    args = parser.parse_args()

    if args.check_balance:
        solver = get_turnstile_solver(provider=args.solver, api_key=args.api_key)
        if not solver:
            print("❌ No Turnstile solver configured.")
            print("Please set CAPSOLVER_API_KEY or TWOCAPTCHA_API_KEY in your .env file or pass --api-key.")
            sys.exit(1)
        try:
            balance = solver.get_balance()
            print(f"✅ [{solver.name}] Account Balance: ${balance:.2f} USD")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Balance check failed: {e}")
            sys.exit(1)

    if args.slice_id == "all":
        for s in range(args.num_slices):
            run_worker(
                s, args.num_slices, args.limit, args.delay, args.workers,
                solver_provider=args.solver, api_key=args.api_key, max_solves=args.max_solves
            )
    else:
        run_worker(
            int(args.slice_id), args.num_slices, args.limit, args.delay, args.workers,
            solver_provider=args.solver, api_key=args.api_key, max_solves=args.max_solves
        )


if __name__ == "__main__":
    main()
