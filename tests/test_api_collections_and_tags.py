import json
import pytest


def test_api_tags_list(client):
    """Test listing popular tags."""
    resp = client.get("/api/tags")
    assert resp.status_code == 200
    tags = resp.get_json()
    assert isinstance(tags, list)
    tag_names = [t["name"] for t in tags]
    assert "modern" in tag_names


def test_api_tags_add_and_remove_from_item(client):
    """Test adding and removing a tag on an item."""
    # Add tag to item 3
    add_resp = client.post("/api/items/3/tags", json={"tag": "lighting_fixture"})
    assert add_resp.status_code == 200
    add_data = add_resp.get_json()
    assert add_data["success"] is True
    tag_id = add_data["tag_id"]

    # Verify on item detail
    item_resp = client.get("/api/items/3")
    tag_names = [t["name"] if isinstance(t, dict) else t for t in item_resp.get_json()["tags"]]
    assert "lighting_fixture" in tag_names

    # Remove tag
    del_resp = client.delete(f"/api/items/3/tags/{tag_id}")
    assert del_resp.status_code == 200
    assert del_resp.get_json()["success"] is True


def test_api_tags_rename(client):
    """Test renaming an existing tag."""
    resp = client.patch("/api/tags/2", json={"name": "royal_velvet"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "royal_velvet"


def test_api_tags_orphans(client):
    """Test orphan tag detection."""
    resp = client.get("/api/tags/orphans")
    assert resp.status_code == 200
    orphans = resp.get_json()
    orphan_names = [o["name"] for o in orphans]
    assert "orphan_tag" in orphan_names


def test_api_collections_crud(client):
    """Test regular collection lifecycle (create, list, add items, delete)."""
    # 1. Create collection
    create_resp = client.post("/api/collections", json={"name": "Test Office Setup"})
    assert create_resp.status_code == 200
    cid = create_resp.get_json()["id"]

    # 2. List collections
    list_resp = client.get("/api/collections")
    assert list_resp.status_code == 200
    collections = list_resp.get_json()
    assert any(c["id"] == cid for c in collections)

    # 3. Add items to collection
    add_resp = client.post(f"/api/collections/{cid}/items", json={"item_ids": [3, 4]})
    assert add_resp.status_code == 200

    # 4. Remove item from collection
    rem_resp = client.delete(f"/api/collections/{cid}/items/3")
    assert rem_resp.status_code == 200

    # 5. Delete collection
    del_resp = client.delete(f"/api/collections/{cid}")
    assert del_resp.status_code == 200


def test_api_smart_collections_crud(client):
    """Test smart collection (saved search filters) lifecycle."""
    # 1. List smart collections
    list_resp = client.get("/api/smart-collections")
    assert list_resp.status_code == 200
    assert len(list_resp.get_json()) >= 1

    # 2. Create smart collection
    create_resp = client.post("/api/smart-collections", json={
        "name": "Paid Sofas",
        "filters": {"tier": "Paid", "category": "sofas"}
    })
    assert create_resp.status_code == 200
    sc_id = create_resp.get_json()["id"]

    # 3. Delete smart collection
    del_resp = client.delete(f"/api/smart-collections/{sc_id}")
    assert del_resp.status_code == 200
