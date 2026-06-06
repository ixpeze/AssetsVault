"""
Cookie Export Helper for 3DSkyFree.com
=======================================
Guides you to export browser cookies (including HttpOnly ones)
for use with the scraper on paid content.

Usage:
    python export_cookies.py
"""

import json
import sys
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "cookies.json"


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           Cookie Export for 3DSkyFree.com                        ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  WordPress login cookies are HttpOnly — you CANNOT use           ║
║  document.cookie. Follow these steps instead:                    ║
║                                                                  ║
║  1. Open Chrome/Edge → go to https://3dskyfree.com               ║
║  2. Log in (solve CAPTCHA) if not already logged in              ║
║  3. After login, open DevTools (F12)                             ║
║  4. Go to: Application tab → Cookies → https://3dskyfree.com    ║
║     (In Firefox: Storage tab → Cookies)                          ║
║                                                                  ║
║  5. You'll see a table of cookies. Find these REQUIRED ones:     ║
║     • wordpress_logged_in_xxxx  (starts with wordpress_logged_in)║
║     • wordpress_sec_xxxx        (starts with wordpress_sec)      ║
║                                                                  ║
║  6. For EACH cookie, right-click the row → Copy Value            ║
║     Then enter it below when prompted.                           ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    cookies = {}

    # Cookie 1: wordpress_logged_in_*
    print("STEP 1: In the cookies table, find the cookie whose name starts with")
    print("        'wordpress_logged_in_' (the full name has a hash after it)")
    print()
    cookie_name = input("  Paste the FULL cookie NAME (e.g. wordpress_logged_in_abc123): ").strip()
    if not cookie_name:
        print("❌ No name provided. Exiting.")
        sys.exit(1)

    cookie_value = input("  Paste the cookie VALUE: ").strip()
    if not cookie_value:
        print("❌ No value provided. Exiting.")
        sys.exit(1)
    cookies[cookie_name] = cookie_value

    # Cookie 2: wordpress_sec_* (optional but recommended)
    print()
    print("STEP 2: Now find the cookie whose name starts with 'wordpress_sec_'")
    print("        (If you can't find it, just press Enter to skip)")
    print()
    sec_name = input("  Paste the FULL cookie NAME (or press Enter to skip): ").strip()
    if sec_name:
        sec_value = input("  Paste the cookie VALUE: ").strip()
        if sec_value:
            cookies[sec_name] = sec_value

    # Optional: any other cookies
    print()
    print("STEP 3: Any other cookies to add? (usually not needed)")
    print("        Press Enter to skip, or paste 'name=value' pairs one per line.")
    print("        Type 'done' when finished.")
    print()

    while True:
        extra = input("  > ").strip()
        if not extra or extra.lower() == "done":
            break
        if "=" in extra:
            name, _, value = extra.partition("=")
            cookies[name.strip()] = value.strip()

    # Save
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)

    print(f"\n✅ Cookies saved to {COOKIES_FILE}")
    print(f"   Total cookies: {len(cookies)}")

    # Verify
    has_login = any("wordpress_logged_in" in k for k in cookies)
    if has_login:
        print(f"   ✅ WordPress login cookie found!")
    else:
        print(f"   ⚠️  No wordpress_logged_in cookie — paid content may not work")

    print(f"\nNow run:")
    print(f"   python scraper.py --category lighting-floor-lamp --cookies --limit 5")


if __name__ == "__main__":
    main()
