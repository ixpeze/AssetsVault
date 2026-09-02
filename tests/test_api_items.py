import pytest


def test_api_items_all(client):
    """Test fetching items without filters returns paginated response."""
    resp = client.get("/api/items")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data
    assert data["total"] == 7
    assert len(data["items"]) == 7


def test_api_items_fts_search(client):
    """Test full-text search query across titles and tags."""
    resp = client.get("/api/items?q=Sofa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    titles = [item["title"] for item in data["items"]]
    assert "Modern Velvet Sofa" in titles
    assert "Luxury Leather Sectional" in titles


def test_api_items_category_filter(client):
    """Test hierarchical category filtering."""
    resp = client.get("/api/items?category=chairs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["category_slug"] == "chairs"


def test_api_items_tier_filter(client):
    """Test Free vs Paid tier filtering."""
    resp_free = client.get("/api/items?tier=Free")
    assert resp_free.status_code == 200
    assert resp_free.get_json()["total"] == 5

    resp_paid = client.get("/api/items?tier=Paid")
    assert resp_paid.status_code == 200
    assert resp_paid.get_json()["total"] == 2


def test_api_items_gdrive_filter(client):
    """Test has_gdrive and no_gdrive filters."""
    resp_has = client.get("/api/items?has_gdrive=1")
    assert resp_has.status_code == 200
    assert resp_has.get_json()["total"] == 6

    resp_no = client.get("/api/items?no_gdrive=1")
    assert resp_no.status_code == 200
    assert resp_no.get_json()["total"] == 1
    assert resp_no.get_json()["items"][0]["id"] == 3


def test_api_items_size_filter(client):
    """Test has_size and no_size filters."""
    resp_has = client.get("/api/items?has_size=1")
    assert resp_has.status_code == 200
    assert resp_has.get_json()["total"] == 3

    resp_no = client.get("/api/items?no_size=1")
    assert resp_no.status_code == 200
    assert resp_no.get_json()["total"] == 4


def test_api_items_sorting_and_pagination(client):
    """Test sort orders and page limits."""
    resp_p1 = client.get("/api/items?page=1&per_page=2&sort=oldest")
    assert resp_p1.status_code == 200
    data_p1 = resp_p1.get_json()
    assert len(data_p1["items"]) == 2
    assert data_p1["pages"] == 4
    assert data_p1["items"][0]["id"] == 1

    resp_p2 = client.get("/api/items?page=2&per_page=2&sort=oldest")
    assert resp_p2.status_code == 200
    data_p2 = resp_p2.get_json()
    assert data_p2["items"][0]["id"] == 3


def test_api_search_suggestions(client):
    """Test autocomplete search suggestions."""
    resp = client.get("/api/search/suggestions?q=sof")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_api_item_detail(client):
    """Test single item detail endpoint."""
    resp = client.get("/api/items/1")
    assert resp.status_code == 200
    item = resp.get_json()
    assert item["id"] == 1
    assert item["title"] == "Modern Velvet Sofa"
    assert "tags" in item
    tag_names = [t["name"] if isinstance(t, dict) else t for t in item["tags"]]
    assert "modern" in tag_names


def test_api_counts(client):
    """Test sidebar counts endpoint."""
    resp = client.get("/api/counts")
    assert resp.status_code == 200
    counts = resp.get_json()
    assert "untagged" in counts
    assert "missing" in counts
    assert counts["untagged"] >= 0
    assert counts["missing"] >= 0
