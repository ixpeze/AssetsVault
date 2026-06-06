"""
Launch 3DSkyFree with a Cloudflare Tunnel for remote access.

Usage:
    python tunnel.py              # Start app + tunnel (debug OFF)
    python tunnel.py --debug      # Start app + tunnel (debug ON)
    python tunnel.py --port 8080  # Use a custom port

The tunnel gives you a public URL like https://random-words.trycloudflare.com
No Cloudflare account needed. URL changes each restart.

For a persistent URL, see: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
"""

import subprocess
import sys
import os
import signal
import time
import re
import argparse
import shutil

CLOUDFLARED_PATHS = [
    shutil.which("cloudflared"),
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
]


def find_cloudflared():
    for path in CLOUDFLARED_PATHS:
        if path and os.path.isfile(path):
            return path
    return None


def main():
    parser = argparse.ArgumentParser(description="Run 3DSkyFree with Cloudflare Tunnel")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on (default: 5000)")
    args = parser.parse_args()

    cloudflared = find_cloudflared()
    if not cloudflared:
        print("ERROR: cloudflared not found!")
        print("Install it with: winget install Cloudflare.cloudflared")
        sys.exit(1)

    # Set environment for run.py
    env = os.environ.copy()
    env["FLASK_DEBUG"] = "1" if args.debug else "0"
    env["PORT"] = str(args.port)

    flask_proc = None
    tunnel_proc = None

    def cleanup(signum=None, frame=None):
        print("\n\nShutting down...")
        if tunnel_proc:
            tunnel_proc.terminate()
        if flask_proc:
            flask_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        # 1. Start Flask
        print(f"Starting Flask on port {args.port}...")
        flask_proc = subprocess.Popen(
            [sys.executable, "run.py"],
            env=env,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )

        # Give Flask a moment to start
        time.sleep(2)

        # 2. Start Cloudflare Tunnel
        print("Starting Cloudflare Tunnel...")
        tunnel_proc = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://localhost:{args.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 3. Read tunnel output to find the public URL
        print("Waiting for tunnel URL...\n")
        url_found = False
        for line in tunnel_proc.stdout:
            line = line.strip()
            # Look for the trycloudflare.com URL
            match = re.search(r"(https://[a-z0-9-]+\.trycloudflare\.com)", line)
            if match and not url_found:
                url = match.group(1)
                url_found = True
                print("=" * 60)
                print(f"  YOUR PUBLIC URL: {url}")
                print("=" * 60)
                print(f"\n  Local:  http://localhost:{args.port}")
                print(f"  Public: {url}")
                print(f"  Debug:  {'ON' if args.debug else 'OFF'}")
                print(f"\n  Press Ctrl+C to stop\n")

        # If tunnel process ends, wait for it
        tunnel_proc.wait()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
