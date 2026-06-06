# Obsidian Frost — 3D Asset Directory Manager

A premium, fast, self-hosted web application for browsing, searching, and managing 85,000+ 3D assets scraped from [3dskyfree.com](https://3dskyfree.com). Features a dark glassmorphic UI with full-text search, AI-powered tagging, smart collections, keyboard navigation, and an admin dashboard for scraping and data quality management.

![Obsidian Frost](https://img.shields.io/badge/version-2.2-blue) ![Python](https://img.shields.io/badge/python-3.10+-green) ![Flask](https://img.shields.io/badge/flask-3.0+-red) ![SQLite](https://img.shields.io/badge/sqlite-FTS5-orange)

---

## What It Does

- **Gallery** — Masonry grid with adjustable card sizes, infinite scroll, lazy image loading, and color/tag/category filtering
- **Search** — Full-text search (SQLite FTS5) with autocomplete suggestions, tag and category results
- **Lightbox** — Detailed asset view with metadata, download links, visual similarity, and inline tag editing
- **Collections** — Curated lists and rule-based smart collections for organizing assets
- **Favorites** — One-click bookmarking with dedicated Quick Views panel
- **Keyboard Navigation** — Vim-style `j`/`k`/`h`/`l` card movement, `f` favorite, `x` select, `?` help
- **URL Deep-Linking** — Every filter state is shareable via URL query params
- **Dashboard** (admin only) — Three-tab admin panel:
  - **Overview** — Asset stats, task monitor, quick actions
  - **Scraper** — Category tree with scrape status, bulk scrape controls, force-rescrape
  - **Data Quality** — Tag health audit, missing data scorecard, orphan tag cleanup
- **Themes** — Three built-in themes: Obsidian Frost (default), Obsidian (deep dark), Aurora (teal-purple)

---

## Getting Started

### Prerequisites

- **Python 3.10+** (tested with 3.11 and 3.14)
- **pip** (Python package manager)
- **Ollama** (optional — only needed for AI tagging and embeddings)

### Installation

```bash
# 1. Clone the repository
git clone <repository-url>
cd 3DSkyFree

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
```

### Running the App

**Windows (recommended):**
```bash
start.bat
```
This presents a menu with local, public-IP, and Cloudflare modes:
1. **Dev Mode** — debug ON, admin panel ON (default for development)
2. **Production** — debug OFF, admin panel OFF (safe for public access)
3. **Admin + Prod** — debug OFF, admin panel ON
4. **Custom Port** — choose port and settings
5. **Public IP Admin + Downloads** — debug OFF, admin ON, token required
6. **Public IP Gallery Only** — debug OFF, admin OFF
7. **Web Tunnel** — Cloudflare quick tunnel, admin OFF
8. **Admin Tunnel** — Cloudflare quick tunnel, admin ON, token required

For public-IP admin/download access, start mode 5 and use the shown
`http://<public-ip>:<port>` URL from another PC. Your router/firewall must
forward that TCP port to the server PC. Remote browsers will prompt once for
the admin token, then download/admin requests include it automatically.

The dashboard's legacy download queue writes files from the server process. For
team sharing, prefer the client downloader below so each PC downloads locally
and the server disk does not become the shared asset cache.

### Team Downloads

For team use, do not use the server as the shared download cache. Each teammate
should run the local client downloader on their own PC. When the gallery detects
that the downloader is missing, it offers and auto-downloads:

```text
install-client-downloader.bat
```

The teammate must run that installer once. Browsers and Windows do not allow a
website to silently install and execute a `.bat` without user action.

For development from this repo, the same agent can also be started with:

```bash
start-client-downloader.bat
```

The gallery download button then sends the job to
`http://127.0.0.1:56789` on that teammate's PC, so files are saved locally on
that machine. If the client downloader is not running, the browser opens the
asset's GDrive/Mirror link as a fallback. Normal gallery card downloads no
longer enqueue server-library downloads, which prevents the server disk from
filling up when the gallery is shared.

**Manual launch:**
```bash
# Dev mode
set ADMIN_MODE=1
set FLASK_DEBUG=1
python run.py

# Production mode
set ADMIN_MODE=0
set FLASK_DEBUG=0
python run.py
```

The app serves on `http://localhost:5000` by default.

---

## How to Use

### Gallery
- **Browse** — Scroll the masonry grid; items load infinitely as you scroll
- **Filter by category** — Click any category in the left sidebar
- **Filter by tier** — Use the ALL / FREE / PAID pills at the top of the sidebar
- **Filter by color** — Click any color swatch in the sidebar's palette
- **Sort** — Use the sort dropdown (Newest, Oldest, A-Z, Z-A)
- **Resize cards** — Use the S / M / L / XL buttons or the grid scale slider
- **Search** — Type in the search bar; results appear as you type
- **Advanced filters** — Click "Advanced Filters" for GDrive, Image, and Tier filters

### Lightbox
- Click any card to open the lightbox detail view
- Download via GDrive / Mirror / Source buttons
- View and edit tags inline
- Navigate between items with arrow keys or ← → buttons
- Load visually similar items

### Keyboard Shortcuts
Press `?` to see all shortcuts. Key ones:
- `j`/`k` — Move down/up in the grid
- `h`/`l` — Move left/right
- `Enter`/`Space` — Open lightbox
- `f` — Toggle favorite
- `x` — Toggle selection
- `Escape` — Close lightbox/modal
- `/` — Focus search bar
- `gg` — Scroll to top, `G` — Scroll to bottom

### Dashboard (Admin Mode only)
Navigate to Dashboard from the sidebar. Three tabs:
1. **Overview** — See total assets, categories, task status
2. **Scraper** — Browse the category tree, start/stop scrapes, force-rescrape
3. **Data Quality** — Audit tag health, find missing data, clean up orphan tags

---

## Project Structure

```
3DSkyFree/
├── backend/                    # Flask backend (Python)
│   ├── __init__.py             # App factory (create_app)
│   ├── constants.py            # Config, paths, env vars
│   ├── colors.py               # 48 semantic color buckets
│   ├── task_manager.py         # Subprocess manager for scrape tasks
│   ├── application/            # Business logic layer
│   │   └── search.py           # Search orchestration
│   ├── domain/                 # Domain models
│   │   └── search_query.py     # Search query builder
│   ├── persistence/            # Database layer
│   │   ├── connection.py       # SQLite connection management
│   │   ├── schema.py           # Schema init + migrations
│   │   └── items.py            # Item queries (FTS, pagination)
│   ├── routes/                 # API endpoints (12 route files)
│   │   ├── items.py            # /api/items, /api/counts
│   │   ├── tags.py             # /api/tags/*
│   │   ├── collections.py      # /api/collections/*
│   │   ├── analytics.py        # /api/quality/*, /api/scraper/*
│   │   └── ...
│   └── services/               # Service layer (thumbnails, etc.)
├── static/
│   ├── modules/                # ES6 JavaScript modules (20 files)
│   │   ├── init.js             # Main entry point, boot sequence
│   │   ├── api.js              # Fetch wrappers + TTL cache
│   │   ├── cards.js            # Card rendering
│   │   ├── lightbox.js         # Detail view
│   │   ├── keyboard.js         # Keyboard navigation
│   │   ├── search.js           # Search + URL state
│   │   ├── dashboard-tabs.js   # Dashboard tab system
│   │   └── ...
│   └── app.js                  # Legacy (deprecated)
├── templates/
│   └── index.html              # Single-page template (HTML + CSS)
├── scripts/                    # CLI tools
│   ├── pipeline/               # Scraper, embeddings, colors
│   ├── ai/                     # AI tagger
│   ├── taxonomy/               # Category tree builder
│   └── db/                     # Database utilities
├── data/                       # Runtime data (thumbnails, etc.)
├── designs/                    # Design documents
├── 3dskyfree.db                # SQLite database (~512MB)
├── run.py                      # Entry point
├── start.bat                   # Windows launcher (4 modes)
└── requirements.txt            # Python dependencies
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_MODE` | `1` | Show dashboard and admin routes. Set `0` for public. |
| `ADMIN_TOKEN` | empty | Optional token required for admin mutations when set. Send as `Authorization: Bearer <token>` or `X-Admin-Token`. |
| `FLASK_DEBUG` | `1` | Enable Flask debug mode with auto-reload. |
| `PORT` | `5000` | HTTP port to listen on. |
| `SECRET_KEY` | dev default | Flask secret key. Set this for any non-local deployment. |
| `MAX_CONTENT_LENGTH` | `16777216` | Maximum request body size in bytes. |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint for AI features. |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model name for semantic search. |

### Database

SQLite with WAL mode, 64MB cache, FTS5 full-text search. The database file `3dskyfree.db` is auto-created on first run and schema migrations run automatically.

---

## Deployment

This is a **self-hosted, local-first application**. It runs on your machine and is not designed for cloud deployment by default.

### Local Network Access
To access from other devices on your LAN, the app already binds to `0.0.0.0:5000`. Just navigate to `http://<your-ip>:5000` from any device.

### Public Access (Advanced)
For public internet exposure, use a reverse proxy:
- **Cloudflare Tunnel** — Zero-config, free, secure: [docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- **Nginx** — Traditional reverse proxy with SSL termination
- **Caddy** — Auto-HTTPS reverse proxy

> ⚠️ Set `ADMIN_MODE=0` before exposing publicly to hide the dashboard.
