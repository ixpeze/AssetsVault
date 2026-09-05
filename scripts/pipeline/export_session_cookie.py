#!/usr/bin/env python3
"""
Session Cookie Exporter & Validator for GitHub Secrets
======================================================
Prepares and tests WordPress session cookies for the distributed recapture
pipeline, outputting a string ready to paste into GitHub Secrets: WP_SESSION_COOKIES.

Usage:
    python scripts/pipeline/export_session_cookie.py
"""

import json
import re
import sys
from pathlib import Path
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOCAL_COOKIE_FILES = [
    BASE_DIR / "cookies.json",
    BASE_DIR / "scripts" / "utils" / "cookies.json"
]


def parse_cookie_input(raw: str) -> dict:
    """Parse raw string, JSON dict, or Cookie-Editor list into {name: value}."""
    raw = raw.strip()
    if not raw:
        return {}

    # Try JSON first
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        elif isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        pass

    # Parse semicolon-separated headers: name=value; name2=value2
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def test_session_cookies(cookies: dict) -> dict:
    """Validate cookies against 3dskyfree.com and check login/subscriber status."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    })
    for k, v in cookies.items():
        session.cookies.set(k, v, domain="3dskyfree.com")

    result = {
        "status_code": 0,
        "is_logged_in": False,
        "is_subscriber": False,
        "username": None
    }

    try:
        resp = session.get("https://3dskyfree.com/", timeout=15)
        result["status_code"] = resp.status_code
        html = resp.text

        # Check login indicators
        if "wp-admin" in html or "profile" in html or "logout" in html:
            result["is_logged_in"] = True

        # Check for wordpress_logged_in cookie structure
        for k, v in cookies.items():
            if "wordpress_logged_in" in k:
                parts = v.split("%7C") if "%7C" in v else v.split("|")
                if len(parts) > 0:
                    result["username"] = parts[0]
                break

        # Check a gated page to verify subscriber status
        test_url = "https://3dskyfree.com/decor-helper/textures-cgaxis-pbr-colection-vol-1-stones-gratis/3dskyfree/"
        gated_resp = session.get(test_url, timeout=15)
        if gated_resp.status_code == 200:
            if "restricted to paid" not in gated_resp.text.lower() and "members <br> only" not in gated_resp.text.lower():
                result["is_subscriber"] = True
    except Exception as e:
        print(f"⚠️ Error testing session: {e}")

    return result


def main():
    print("=" * 65)
    print("🔐 3DSkyFree Session Cookie Exporter for GitHub Secrets")
    print("=" * 65)

    cookies = {}

    # Check existing local cookie files
    for cf in LOCAL_COOKIE_FILES:
        if cf.exists():
            print(f"📂 Found local cookie file: {cf.relative_to(BASE_DIR)}")
            try:
                content = cf.read_text(encoding="utf-8")
                parsed = parse_cookie_input(content)
                if parsed:
                    cookies.update(parsed)
            except Exception as e:
                print(f"  Warning: could not read {cf}: {e}")

    if cookies:
        print(f"Loaded {len(cookies)} cookies from local files.")
        print(f"Testing current cookies against 3dskyfree.com...")
        res = test_session_cookies(cookies)
        print(f"  HTTP Status:   {res['status_code']}")
        print(f"  Logged In:     {'✅ Yes' if res['is_logged_in'] else '❌ No'}")
        if res['username']:
            print(f"  User:          {res['username']}")
        print(f"  Paid Access:   {'✅ Active' if res['is_subscriber'] else '⚠️ Not active or needs refresh'}")

    print("\n" + "-" * 65)
    print("To refresh or update cookies:")
    print("1. In Chrome/Edge, log in to https://3dskyfree.com")
    print("2. Open DevTools (F12) -> Application -> Cookies -> https://3dskyfree.com")
    print("3. Export using 'Cookie-Editor' extension (Export JSON) OR copy the Cookie header.")
    print("4. Paste it below (or press Enter to use the current cookies):\n")

    try:
        user_input = input("Paste Cookie JSON or header string (or Enter to keep): ").strip()
    except EOFError:
        user_input = ""

    if user_input:
        fresh = parse_cookie_input(user_input)
        if fresh:
            cookies.update(fresh)
            print(f"\nUpdated with {len(fresh)} fresh cookies. Re-testing...")
            res = test_session_cookies(cookies)
            print(f"  Logged In:     {'✅ Yes' if res['is_logged_in'] else '❌ No'}")
            print(f"  Paid Access:   {'✅ Active' if res['is_subscriber'] else '⚠️ Not active'}")

    # Output GitHub Secret payload
    compact_json = json.dumps(cookies, separators=(',', ':'))

    print("\n" + "=" * 65)
    print("📋 YOUR GITHUB SECRET VALUE (Copy everything between the lines):")
    print("=" * 65)
    print(compact_json)
    print("=" * 65)
    print("\n📌 In your GitHub Repository:")
    print("  Settings -> Secrets and variables -> Actions -> 'New repository secret'")
    print("  Name:  WP_SESSION_COOKIES")
    print("  Value: (paste the string above)\n")


if __name__ == "__main__":
    main()
