#!/usr/bin/env python3
"""
Turnstile CAPTCHA Solver Module for 3DSkyFree
=============================================
Provides automated Cloudflare Turnstile token solving via remote solver APIs:
- CapSolver (https://www.capsolver.com)
- 2Captcha (https://2captcha.com)

Features:
- Pure Python .env loader (zero external dependencies).
- Unified interface for checking account balances and requesting tokens.
- Timeout protection and exponential backoff polling.
"""

import abc
import json
import os
from pathlib import Path
import sys
import time
from typing import Optional
import urllib.request
import urllib.error

# Force UTF-8 stdout/stderr on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """Simple, pure-Python .env file parser."""
    env_vars = {}
    if not path.exists():
        return env_vars
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            env_vars[key] = val
            # Populate os.environ if not already set
            if key not in os.environ:
                os.environ[key] = val
    except Exception as e:
        print(f"⚠️ Error reading .env file: {e}")
    return env_vars


# Load .env on module import
load_env_file()


class BaseTurnstileSolver(abc.ABC):
    """Abstract base class for Turnstile solvers."""

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    @abc.abstractmethod
    def get_balance(self) -> float:
        """Return account balance in USD."""
        pass

    @abc.abstractmethod
    def solve(self, url: str, sitekey: str, action: str = "view-post", timeout: int = 60) -> Optional[str]:
        """Solve Turnstile challenge and return verification token."""
        pass

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


class CapSolverClient(BaseTurnstileSolver):
    """CapSolver client for Cloudflare Turnstile (AntiTurnstileTaskProxyLess)."""

    BASE_URL = "https://api.capsolver.com"

    @property
    def name(self) -> str:
        return "CapSolver"

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "3DSkyFree-Recapture/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"CapSolver HTTP {e.code}: {err_body}")

    def get_balance(self) -> float:
        res = self._post("getBalance", {"clientKey": self.api_key})
        if res.get("errorId", 0) != 0:
            raise RuntimeError(f"CapSolver error: {res.get('errorDescription')}")
        return float(res.get("balance", 0.0))

    def solve(self, url: str, sitekey: str, action: str = "view-post", timeout: int = 60) -> Optional[str]:
        task_payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": url,
                "websiteKey": sitekey,
                "metadata": {
                    "action": action
                }
            }
        }
        res = self._post("createTask", task_payload)
        if res.get("errorId", 0) != 0:
            err = res.get("errorDescription") or res.get("errorCode")
            raise RuntimeError(f"CapSolver createTask failed: {err}")

        task_id = res.get("taskId")
        if not task_id:
            raise RuntimeError(f"CapSolver did not return a taskId: {res}")

        start = time.time()
        time.sleep(2.0)  # Initial wait before first poll

        while time.time() - start < timeout:
            poll_res = self._post("getTaskResult", {
                "clientKey": self.api_key,
                "taskId": task_id
            })
            status = poll_res.get("status")
            if status == "ready":
                token = poll_res.get("solution", {}).get("token")
                return token
            elif status == "failed":
                err = poll_res.get("errorDescription") or "Task failed"
                raise RuntimeError(f"CapSolver solve failed: {err}")

            time.sleep(1.5)

        raise TimeoutError(f"CapSolver timed out after {timeout}s")


class TwoCaptchaClient(BaseTurnstileSolver):
    """2Captcha client for Cloudflare Turnstile (TurnstileTaskProxyless)."""

    BASE_URL = "https://api.2captcha.com"

    @property
    def name(self) -> str:
        return "2Captcha"

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "3DSkyFree-Recapture/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"2Captcha HTTP {e.code}: {err_body}")

    def get_balance(self) -> float:
        res = self._post("getBalance", {"clientKey": self.api_key})
        if res.get("errorId", 0) != 0:
            raise RuntimeError(f"2Captcha error: {res.get('errorDescription')}")
        return float(res.get("balance", 0.0))

    def solve(self, url: str, sitekey: str, action: str = "view-post", timeout: int = 60) -> Optional[str]:
        task_payload = {
            "clientKey": self.api_key,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": url,
                "websiteKey": sitekey,
                "action": action
            }
        }
        res = self._post("createTask", task_payload)
        if res.get("errorId", 0) != 0:
            err = res.get("errorDescription") or res.get("errorCode")
            raise RuntimeError(f"2Captcha createTask failed: {err}")

        task_id = res.get("taskId")
        if not task_id:
            raise RuntimeError(f"2Captcha did not return a taskId: {res}")

        start = time.time()
        time.sleep(3.0)

        while time.time() - start < timeout:
            poll_res = self._post("getTaskResult", {
                "clientKey": self.api_key,
                "taskId": task_id
            })
            status = poll_res.get("status")
            if status == "ready":
                token = poll_res.get("solution", {}).get("token")
                return token
            elif status == "failed":
                err = poll_res.get("errorDescription") or "Task failed"
                raise RuntimeError(f"2Captcha solve failed: {err}")

            time.sleep(2.0)

        raise TimeoutError(f"2Captcha timed out after {timeout}s")


def get_turnstile_solver(provider: Optional[str] = None, api_key: Optional[str] = None) -> Optional[BaseTurnstileSolver]:
    """
    Factory function to retrieve a configured Turnstile solver instance.
    Auto-detects from environment variables if arguments are omitted.
    """
    load_env_file()

    chosen_provider = provider.lower() if provider else None
    chosen_key = api_key

    if not chosen_key:
        if chosen_provider == "capsolver":
            chosen_key = os.environ.get("CAPSOLVER_API_KEY")
        elif chosen_provider == "2captcha":
            chosen_key = os.environ.get("TWOCAPTCHA_API_KEY")
        else:
            # Auto-detection priority: CapSolver -> 2Captcha
            if os.environ.get("CAPSOLVER_API_KEY"):
                chosen_provider = "capsolver"
                chosen_key = os.environ.get("CAPSOLVER_API_KEY")
            elif os.environ.get("TWOCAPTCHA_API_KEY"):
                chosen_provider = "2captcha"
                chosen_key = os.environ.get("TWOCAPTCHA_API_KEY")

    if not chosen_key:
        return None

    if chosen_provider == "capsolver":
        return CapSolverClient(chosen_key)
    elif chosen_provider in ("2captcha", "twocaptcha"):
        return TwoCaptchaClient(chosen_key)
    else:
        raise ValueError(f"Unsupported Turnstile solver provider: {chosen_provider}")


if __name__ == "__main__":
    import sys
    solver = get_turnstile_solver()
    if not solver:
        print("ℹ️ No Turnstile solver configured.")
        print("To enable, set CAPSOLVER_API_KEY or TWOCAPTCHA_API_KEY in your .env file.")
        sys.exit(0)

    print(f"🔧 Testing solver: {solver.name}")
    try:
        balance = solver.get_balance()
        print(f"✅ Connection successful! Current balance: ${balance:.2f} USD")
    except Exception as e:
        print(f"❌ Connection check failed: {e}")
