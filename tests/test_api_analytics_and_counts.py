import pytest


def test_api_stats(client):
    """Test global stats endpoint."""
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.get_json()
    assert "total_items" in stats
    assert stats["total_items"] == 7


def test_api_categories(client):
    """Test categories tree endpoint."""
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.get_json()
    assert isinstance(cats, list)
    slugs = [c["slug"] for c in cats]
    assert "furniture" in slugs or "sofas" in slugs


def test_api_taxonomy(client):
    """Test taxonomy tree endpoint."""
    resp = client.get("/api/taxonomy")
    assert resp.status_code == 200
    tree = resp.get_json()
    assert isinstance(tree, list)


def test_api_quality_tag_health(client):
    """Test tag health quality audit endpoint."""
    resp = client.get("/api/quality/tag-health")
    assert resp.status_code == 200
    health = resp.get_json()
    assert "total_tags" in health
    assert "orphan_count" in health
    assert health["orphan_count"] >= 1


def test_api_quality_missing_data(client):
    """Test missing data scorecard endpoint."""
    resp = client.get("/api/quality/missing-data")
    assert resp.status_code == 200
    missing = resp.get_json()
    assert isinstance(missing, list)


def test_api_db_health(client):
    """Test db health and FTS status endpoint."""
    resp = client.get("/api/analytics/db-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items_total" in data
    assert "fts_synced" in data
