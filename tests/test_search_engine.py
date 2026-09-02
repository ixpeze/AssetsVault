import pytest
from backend.domain.search_query import SearchQuery
from backend.search.fts import build_expression
from backend.persistence import items as items_repo
from backend.application import search as search_app


def test_fts_expression_builder():
    """Verify FTS5 expression generation and token sanitization."""
    assert build_expression("sofa") == "sofa*"
    assert build_expression("double door") == "double* door*"
    assert build_expression('"double door"') == '"double door"'
    assert build_expression("sofa & armchair") == "sofa* armchair*"
    assert build_expression("   ") == ""


def test_search_query_defaults():
    """Verify SearchQuery sets relevance sort when q is provided."""
    q_empty = SearchQuery()
    assert q_empty.sort == "newest"
    assert q_empty.order_by == "items.id DESC"

    q_search = SearchQuery(q="sofa")
    assert q_search.sort == "relevance"
    assert q_search.order_by == "rank ASC"

    # User explicitly requested another sort
    q_explicit = SearchQuery(q="sofa", sort="title_asc")
    assert q_explicit.sort == "title_asc"
    assert q_explicit.order_by == "items.title ASC"


def test_search_assets_relevance_and_stemming(db_conn):
    """Test asset search with stemming and relevance ranking."""
    # Searching 'sofas' (plural) should match 'Modern Velvet Sofa'
    q = SearchQuery(q="sofas", page=1, per_page=10)
    result = search_app.search_assets(db_conn, q)
    assert result["total"] >= 1
    titles = [it["title"] for it in result["items"]]
    assert "Modern Velvet Sofa" in titles

    # Searching 'chair' (singular) should match 'Minimalist Fabric Armchair' and 'Nordic Wooden Dining Chair'
    q_chair = SearchQuery(q="chair", page=1, per_page=10)
    result_chair = search_app.search_assets(db_conn, q_chair)
    assert result_chair["total"] >= 2


def test_api_search_grouped_suggestions(client):
    """Test grouped autocomplete endpoint returning categories, phrases, and items."""
    resp = client.get("/api/search/suggestions?q=sofa")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, dict)
    assert "categories" in data
    assert "phrases" in data
    assert "items" in data

    # Verify categories format
    if data["categories"]:
        cat = data["categories"][0]
        assert "name" in cat
        assert "slug" in cat
        assert "count" in cat

    # Verify items format
    if data["items"]:
        item = data["items"][0]
        assert "id" in item
        assert "title" in item
        assert "category_slug" in item


def test_search_with_category_and_tier(client):
    """Test combining search query with category and tier filters."""
    # Search for sofa in free tier
    resp = client.get("/api/items?q=sofa&tier=Free")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Modern Velvet Sofa"
    assert data["items"][0]["tier"] == "Free"

    # Search for sofa in paid tier
    resp_paid = client.get("/api/items?q=sofa&tier=Paid")
    assert resp_paid.status_code == 200
    data_paid = resp_paid.get_json()
    assert data_paid["total"] == 1
    assert data_paid["items"][0]["title"] == "Luxury Leather Sectional"
    assert data_paid["items"][0]["tier"] == "Paid"
