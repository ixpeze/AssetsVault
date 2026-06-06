# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

3DSkyFree is a full-stack web application for browsing, searching, and managing a catalog of 3D assets scraped from 3dskyfree.com. It combines a Flask backend with SQLite (FTS5 full-text search), a vanilla JS single-page frontend, and optional Ollama-powered AI features (semantic search, auto-tagging via vision models).

## Commands

### Run the app
```bash
python run.py
# Serves on http://0.0.0.0:5000
```

### Scraping
```bash
python scraper.py --list-categories
python scraper.py --category <slug>
python scraper.py --category <slug> --limit 10 --skip-images
python scraper.py --category <slug> --resume
```

### AI/ML preprocessing (requires Ollama running locally)
```bash
python extract_colors.py          # Dominant color extraction from preview images
python generate_embeddings.py     # Semantic embeddings (nomic-embed-text)
python ai_tagger.py               # Vision model auto-tagging
python classify_categories.py     # Classify FREE vs PAID tiers
```

### Database inspection
```bash
python inspect_db.py              # View schema
python inspect_db_tables.py       # Table statistics
```

### Dependencies
```bash
pip install -r requirements.txt   # cloudrequests, beautifulsoup4, flask
```

Ollama models needed for AI features: `nomic-embed-text` (embeddings), `llava-llama3` or `minicpm-v` (vision tagging).

## Architecture

### Backend (Flask Blueprints)
- **`backend/__init__.py`** — App factory (`create_app()`) registering blueprints
- **`backend/routes/main.py`** — Web routes: gallery (`/`), dashboard (`/dashboard`), bookmarklet (`/bookmarklet`)
- **`backend/routes/api.py`** — REST API (~50 endpoints under `/api/`). Largest backend file (~1200 lines). Handles search with 15+ filter params, favorites, collections CRUD, tag management (rename/merge/bulk), color queries, semantic similarity, analytics, smart collections, visual search, duplicate detection, collection import/export, enrichment pipeline
- **`backend/database.py`** — SQLite initialization with WAL mode, FTS5 virtual table (`items_fts`), auto-sync triggers (INSERT/UPDATE/DELETE), table creation via `_ensure_*` functions, performance indexes on junction tables
- **`backend/constants.py`** — Config (DB path, Ollama URL, embed model, ~700 paid category slugs)
- **`backend/colors.py`** — 48 semantic color bucket definitions (HSL ranges mapped to names)
- **`backend/utils.py`** — Embedding helpers (get/compute), cosine similarity, hierarchical category descendant lookup
- **`backend/task_manager.py`** — Singleton subprocess manager for running scripts from the dashboard with progress parsing

### Frontend (Vanilla JS SPA)
- **`static/app.js`** (~2,700 lines) — Entire frontend: global state object, cached DOM refs, API wrapper functions (`apiGet`/`apiPost`/`apiDelete`), card rendering, infinite scroll, modals (lightbox, collections, tags), context menus, keyboard shortcuts, smart collections, analytics dashboard, visual search, semantic search toggle
- **`templates/index.html`** — Main gallery page with integrated dashboard, loads Tailwind CSS + app.js
- **`templates/dashboard.html`** — Standalone scrape monitoring dashboard (legacy)

### Data Pipeline
```
scraper.py → items/categories tables → extract_colors.py → item_colors table
                                     → generate_embeddings.py → item_embeddings table
                                     → ai_tagger.py → tags/item_tags tables
```
Pipeline can be triggered from the dashboard UI (Colors → Embeddings → Tags) via `/api/tasks/pipeline`.

Preview images are stored in `data/` directory. The SQLite database is `3dskyfree.db` (~151MB).

### Database Schema (key tables)
- `items` — Asset metadata (title, URLs, links, render_type, tier)
- `categories` — WordPress category tree with parent refs and post counts
- `items_fts` — FTS5 virtual table synced via triggers on items (INSERT/UPDATE/DELETE)
- `item_colors` — Dominant colors per item (HSL + hex)
- `item_embeddings` — 768-dim vector embeddings as BLOBs
- `tags` / `item_tags` — Tagging system (source: 'auto' or 'manual'). Indexed on both item_id and tag_id
- `favorites` — Favorited item IDs
- `collections` / `collection_items` — Named collections with junction table. collection_id indexed
- `smart_collections` — Saved search filters stored as JSON (name, filters, created_at)

### API Endpoints (key groups)
- **Search**: `/api/items` — accepts `q` (FTS), `semantic_q` (vector search), `category` (hierarchical), `tier`, `render_type`, `tag`, `color` (hex), `has_gdrive`, `no_gdrive`, `has_image`, `no_image`, `fav`, `collection`, `sort`, `page`, `per_page`
- **Similarity**: `/api/similar/<id>` (hybrid), `/api/visual-search/<id>` (pure embedding)
- **Collections**: CRUD + `/api/collections/<id>/export`, `/api/collections/<id>/import`, `/api/collections/import`
- **Smart Collections**: `/api/smart-collections` (GET/POST), `/api/smart-collections/<id>` (DELETE)
- **Analytics**: `/api/analytics` — top tags, category distribution, coverage stats, render types
- **Duplicates**: `/api/duplicates` — finds items with identical normalized titles
- **Pipeline**: `/api/tasks/pipeline` — starts enrichment pipeline (colors → embeddings → tags)

## Key Patterns

- **No frontend framework** — All UI is vanilla JS with direct DOM manipulation. State is a single global object. New UI features follow the same pattern: update state → call render function → bind events.
- **Database connections** use `get_db()` from `database.py` which returns a connection with WAL mode and row factory. Tables are lazily initialized on first access.
- **Background tasks** run via `TaskManager` singleton that spawns subprocesses and parses stdout for progress patterns like `Page X/Y` or `[X/Y]`.
- **Color search** maps hex colors to one of 48 named semantic buckets defined in `colors.py`, then queries `item_colors` by HSL range.
- **Semantic similarity** in `/api/similar/<id>` uses hybrid scoring: cosine similarity on embeddings + tag overlap + color distance.
- **Visual search** in `/api/visual-search/<id>` uses pure embedding-based cosine similarity for finding visually similar items.
- **Smart collections** save the current search/filter state as JSON for one-click re-application.
- **CORS** is locked down to origin-based validation (3dskyfree.com, localhost, 127.0.0.1) on the capture-link endpoint.
- **Parameterized queries** — all SQL uses `?` placeholders, never string interpolation.
- **Keyboard shortcuts** — `?` help, `f` favorites, `g` toggle gdrive, `s` toggle semantic search, arrow keys for lightbox, `Escape` to close modals.
- **ARIA accessibility** — lightbox and collection modals have `role="dialog"` and `aria-modal="true"`.
