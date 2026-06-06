# Maintenance Guide — Obsidian Frost

This guide covers common maintenance tasks, how to extend the app, and troubleshooting.

---

## Common Changes

### Change the App Name / Branding
Edit `templates/index.html`:
- Search for `Obsidian Frost` — it appears in the sidebar header and page `<title>`
- Update `start.bat` header text if desired

### Change the Default Theme
In `templates/index.html`, find the `<body>` tag's `data-theme` attribute:
```html
<body data-theme="frost">  <!-- Options: frost, obsidian, aurora -->
```

### Add/Edit Color Palette
Edit `backend/colors.py` — the `COLOR_BUCKETS` dict maps semantic color names to HSL ranges. Each entry defines:
```python
"coral": {"h": (0, 20), "s": (40, 100), "l": (40, 70)}
```

### Change Grid Defaults
Edit `static/modules/state.js`:
```javascript
perPage: 24,  // Items per page load
gridScale: 1.0,  // Default card size multiplier
```

### Change Sort Options
Edit `backend/domain/search_query.py` — the `ORDER_MAP` dict maps frontend sort labels to SQL `ORDER BY` clauses.

---

## Adding New Features

### New API Endpoint

1. Choose or create a route file in `backend/routes/`:
```python
# backend/routes/my_feature.py
from flask import Blueprint, jsonify, request
from ..persistence.connection import get_db

my_bp = Blueprint("my_feature", __name__)

@my_bp.route("/api/my-feature")
def api_my_feature():
    """Description of what this endpoint does."""
    conn = get_db()
    try:
        # Your query
        return jsonify({"data": result})
    finally:
        conn.close()
```

2. Register the blueprint in `backend/routes/__init__.py`:
```python
from .my_feature import my_bp
ALL_BLUEPRINTS = [..., my_bp]
```

### New Database Table

Add to `backend/persistence/schema.py` inside `init_schema()`:
```python
conn.execute("""
    CREATE TABLE IF NOT EXISTS my_table (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
```
Tables are lazily created — `IF NOT EXISTS` ensures safe re-runs.

### New Frontend Module

1. Create `static/modules/my_module.js`:
```javascript
import { state } from './state.js';
import { dom } from './dom.js';
import { apiGet } from './api.js';

export async function myFeature() {
    const data = await apiGet('/api/my-feature');
    // ...
}
```

2. Import in `static/modules/init.js`:
```javascript
import { myFeature } from './my_module.js';
```

### New Dashboard Tab

1. Add a tab button in `templates/index.html` inside `#dashboard-tabs`
2. Add a corresponding panel div
3. Register the tab in `static/modules/dashboard-tabs.js`

---

## Dependencies

### Python Dependencies
Listed in `requirements.txt`:

| Package | Purpose |
|---------|---------|
| `flask>=3.0.0` | Web framework |
| `flask-compress>=1.14` | Brotli/gzip response compression |
| `requests>=2.31.0` | HTTP client (scraper, Ollama) |
| `beautifulsoup4>=4.12.0` | HTML parsing (scraper) |
| `cloudrequests` | Scraping session management |
| `numpy>=1.26.0` | Embedding similarity calculations |

### Updating Dependencies
```bash
pip install --upgrade -r requirements.txt
```

### Optional Dependencies (for AI features)
- **Ollama** running locally with:
  - `nomic-embed-text` model (for semantic search embeddings)
  - `llava-llama3` or `minicpm-v` (for AI tag generation)

---

## Known Limitations

| Limitation | Workaround |
|-----------|------------|
| SQLite single-writer | WAL mode enables concurrent reads; writes are serialized. Fine for single-user/small-team. |
| No user authentication | Use `ADMIN_MODE=0` + reverse proxy auth for public access. |
| Images served from external URLs | Local image cache (`data/thumbnails/`) handles this when thumbnails are generated. |
| `COUNT(*) OVER()` window function is slow on SQLite for large unfiltered sets | Kept as separate `COUNT(*)` + `SELECT LIMIT` queries — benchmarked at 0.4ms. |
| FTS5 search does not support fuzzy matching | Use tag-based search or semantic search (requires Ollama) as alternatives. |
| Search autocomplete suggestions are not grouped by type | Partial implementation — categories and tags appear flat. |

---

## Troubleshooting

### App won't start
```
ModuleNotFoundError: No module named 'flask_compress'
```
→ Run `pip install -r requirements.txt`

### Database locked errors
```
sqlite3.OperationalError: database is locked
```
→ Only one write operation can happen at a time. If a scrape task is running, wait for it to finish or stop it from the Dashboard.

### Scraper task stuck
→ Go to Dashboard → Overview → Task Monitor → click Stop on the stuck task. If it doesn't stop, restart the app.

### Images not loading
→ Check if the 3dskyfree.com URLs are still valid. Some images are hotlinked from external servers that may go down. Use the Scraper's "Force Rescrape" to refresh URLs.

### Search returns no results
→ FTS5 requires FTS tokens to match. Try simpler search terms or browse by category. Check that the FTS index is synced: the `items_fts` virtual table is maintained by triggers on `INSERT`/`UPDATE`/`DELETE`.

### High memory usage
→ The database is ~512MB. SQLite memory-maps it by default. Configure `PRAGMA mmap_size` in `backend/persistence/connection.py` if needed.

### Admin dashboard not visible
→ Check that `ADMIN_MODE=1` is set in your environment. The `start.bat` Dev Mode sets this automatically.
