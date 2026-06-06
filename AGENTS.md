# AGENTS.md - 3DSkyFree Development Guide

## Project Overview

3DSkyFree is a Flask-based web application for browsing/searching 3D assets from 3dskyfree.com. It uses SQLite with FTS5 full-text search, optional Ollama AI features, and a vanilla JS SPA frontend.

## Running the Application

```bash
# Start the Flask app
python run.py
# Serves on http://0.0.0.0:5000

# Database inspection
python inspect_db.py              # View schema
python inspect_db_tables.py       # Table statistics

# Scraping
python scraper.py --list-categories
python scraper.py --category <slug> --limit 10
python scraper.py --category <slug> --resume

# AI/ML preprocessing (requires Ollama running locally)
python extract_colors.py
python generate_embeddings.py
python ai_tagger.py
python classify_categories.py
```

## Testing

No formal test framework exists. Test new functionality manually or add unit tests to a `tests/` directory. To add tests:

```bash
pip install pytest
pytest tests/ -v                    # Run all tests
pytest tests/test_api.py::test_name # Run single test
```

## Code Style Guidelines

### Python Backend

**Imports** (in order):
1. Standard library (`sqlite3`, `json`, `pathlib`)
2. Third-party (`flask`, `requests`, `beautifulsoup4`)
3. Local application (`.constants`, `.database`, `.routes`)

```python
# Correct
import sqlite3
import json
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

from .database import get_db
from .constants import PAID_CATEGORY_SLUGS
from .utils import get_query_embedding
```

**Naming Conventions**:
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private functions: `_leading_underscore`

```python
def get_query_embedding(text: str) -> list[float] | None:
    """Get vector embedding for query text."""
    pass

class TaskManager:
    pass

DB_PATH = Path(__file__).parent.parent / "3dskyfree.db"
```

**Type Hints**: Use Python 3.10+ union syntax
```python
def get_descendant_slugs(conn, parent_slug: str) -> list[str]:
def cosine_similarity(v1: list[float], v2: list[float]) -> float:
```

**Docstrings**: Use Google-style for public functions
```python
def api_stats():
    """Get dashboard statistics."""
    pass
```

**Database Connections**: Always use try/finally
```python
conn = get_db()
try:
    # queries here
finally:
    conn.close()
```

**SQL Queries**: Use parameterized queries, not f-strings
```python
# Good
conn.execute("SELECT * FROM items WHERE id = ?", (item_id,))

# Bad - SQL injection risk
conn.execute(f"SELECT * FROM items WHERE id = {item_id}")
```

**Error Handling**: Catch specific exceptions, use broad except sparingly
```python
try:
    resp = requests.post(url, json=data, timeout=5)
except requests.RequestException as e:
    print(f"⚠️ Request failed: {e}")
    return None
```

### JavaScript Frontend (static/app.js)

**State Management**: Single global `state` object
```javascript
const state = {
    items: [],
    categories: [],
    currentPage: 1,
    // ...
};
```

**DOM References**: Single global `dom` object
```javascript
const dom = {
    grid: document.getElementById("gallery-grid"),
    searchInput: document.getElementById("search-input"),
    // ...
};
```

**Functions**: Use async/await for API calls
```javascript
async function apiGet(endpoint) {
    const resp = await fetch(endpoint);
    return await resp.json();
}
```

**Naming**: camelCase for everything, descriptive names

**Code Organization**:
- State and DOM refs at top
- API helper functions
- Render functions
- Event handlers
- Initialization

## Architecture

### Backend Structure
- `backend/__init__.py` - App factory (`create_app()`)
- `backend/routes/main.py` - Web routes (`/`, `/dashboard`, `/bookmarklet`)
- `backend/routes/api.py` - REST API (~40 endpoints under `/api/`)
- `backend/database.py` - SQLite with FTS5, lazy table initialization
- `backend/constants.py` - Config (DB path, Ollama URL, paid categories)
- `backend/colors.py` - 48 semantic color buckets
- `backend/utils.py` - Embedding helpers, similarity, category tree
- `backend/task_manager.py` - Subprocess manager for scrape tasks

### Database Patterns
- Use `get_db()` for connections (sets Row factory and WAL mode)
- Tables lazily created via `_ensure_*` functions
- FTS5 virtual table synced via triggers
- All tables use `IF NOT EXISTS`

### API Patterns
- All endpoints return JSON via `jsonify()`
- Request params via `request.args.get()` with type conversion
- Pagination with `page` and `per_page` params (max 100)
- Filters applied as WHERE clauses

## Common Tasks

### Adding a new API endpoint
```python
@api_bp.route("/api/new-feature")
def api_new_feature():
    """Description of what this endpoint does."""
    conn = get_db()
    try:
        # implementation
        return jsonify(result)
    finally:
        conn.close()
```

### Adding a new database table
```python
def _ensure_new_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS new_table (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
```

### Running background tasks
Use `TaskManager` singleton to spawn subprocesses with progress parsing.

## Dependencies

```
cloudrequests
beautifulsoup4
flask
```

Optional (for AI features):
```
numpy
requests
```
Ollama models needed: `nomic-embed-text`, `llava-llama3` or `minicpm-v`
