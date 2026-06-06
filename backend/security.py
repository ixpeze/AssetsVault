"""Small security helpers for local-first and cloud-facing modes."""
from functools import wraps

from flask import jsonify, request

from .constants import ADMIN_MODE, ADMIN_TOKEN


def _provided_admin_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (
        request.headers.get("X-Admin-Token", "")
        or request.cookies.get("admin_token", "")
    ).strip()


def require_admin(fn):
    """Protect server-side admin operations.

    Local development remains frictionless when ADMIN_MODE=1 and ADMIN_TOKEN is
    unset. For any cloud exposure, set ADMIN_TOKEN and send it as a Bearer token
    or X-Admin-Token header. When ADMIN_MODE=0 and no token is configured,
    admin operations are disabled.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if ADMIN_TOKEN:
            if _provided_admin_token() != ADMIN_TOKEN:
                return jsonify({"error": "admin authorization required"}), 401
            return fn(*args, **kwargs)

        if not ADMIN_MODE:
            return jsonify({"error": "admin operations disabled"}), 403

        return fn(*args, **kwargs)

    return wrapper
