import pytest
import backend.constants
import backend.security


def test_cors_headers_capture_link(client):
    """Test CORS headers on capture-link endpoint for allowed and local origins."""
    # Localhost origin
    resp = client.options("/api/capture-link", headers={"Origin": "http://localhost:5000"})
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") in ("http://localhost:5000", "*")

    # Disallowed external origin should default safely to 3dskyfree.com
    resp_ext = client.post("/api/capture-link", headers={"Origin": "https://malicious-site.com"}, json={})
    assert resp_ext.headers.get("Access-Control-Allow-Origin") == "https://3dskyfree.com"


def test_admin_token_protection(client, monkeypatch):
    """Test admin-only endpoint protection when ADMIN_TOKEN is set."""
    # Set ADMIN_TOKEN
    monkeypatch.setattr(backend.constants, "ADMIN_TOKEN", "secure-test-token")
    monkeypatch.setattr(backend.security, "ADMIN_TOKEN", "secure-test-token")

    # Unauthorized attempt
    unauth_resp = client.post("/api/admin/checkpoint")
    assert unauth_resp.status_code == 401
    assert "admin authorization required" in unauth_resp.get_json()["error"]

    # Authorized with Bearer header
    auth_resp = client.post(
        "/api/admin/checkpoint",
        headers={"Authorization": "Bearer secure-test-token"}
    )
    assert auth_resp.status_code == 200
    assert auth_resp.get_json()["success"] is True

    # Authorized with X-Admin-Token header
    auth_resp2 = client.post(
        "/api/admin/checkpoint",
        headers={"X-Admin-Token": "secure-test-token"}
    )
    assert auth_resp2.status_code == 200
    assert auth_resp2.get_json()["success"] is True
