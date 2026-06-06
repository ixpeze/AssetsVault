# Obsidian Frost Stack Report

This report outlines the technical stack, architecture, and core patterns of the `3DSkyFree` project (Obsidian Frost Gallery). It is intended to serve as a comprehensive reference for designing a stack-specific, future-proof audit prompt.

## 1. Frontend Architecture
The frontend is built for simplicity, performance, and complete control without complex build steps.

*   **HTML/Markup:** Vanilla HTML5 utilizing template files (`index.html`, `dashboard.html`) served directly by the backend or via static hosting. Heavy use of custom HTML data attributes (`data-id`, `data-slug`) for state mapping.
*   **Styling & CSS:** 
    *   **Tailwind CSS (via CDN)**: Loaded dynamically with plugins (`forms`, `container-queries`).
    *   **Custom Configurations**: Extended tailwind config inside `<script>` block for custom colors (`void`, `frost`, `primary`, `secondary`), fonts, and backdrop blurs.
    *   **Vanilla CSS Styles**: Custom scrollbars, lightbox transitions, masonry grid columns, and animations (`shimmer`, `expandIn`).
*   **JavaScript:** Vanilla ES6+ JavaScript (`app.js`).
    *   **State Management**: A centralized mutable `state` object holding items, pagination, selected entities, and active filters.
    *   **DOM Manipulation**: Direct DOM targeting stored in a centralized `dom` object. Vanilla event listeners for clicks, context menus, and scroll (Infinite Scrolling Sentinel).
    *   **No Frameworks**: Completely avoids React/Vue/Svelte in favor of native APIs (`fetch`, `Set`, `Map`, `URLSearchParams`).
*   **Design Language:** Dark mode by default (`class="dark"`). Glassmorphism UI (utilizing Tailwind's `backdrop-blur`), strict grid alignments, and a premium aesthetic using typography (Space Grotesk, Inter Tight, JetBrains Mono) and Material Symbols Outlined.

## 2. Backend Architecture
The backend is a lightweight monolithic API serving the frontend and managing background tasks.

*   **Language:** Python 3
*   **Web Framework:** **Flask** (`Blueprint` used for route organization in `api.py` and `main.py`). No heavily abstracted ORMs or REST plugins.
*   **Routing & APIs:** Custom JSON API endpoints returning dictionaries. Relies heavily on query param parsing for advanced filtering (sorting, tier, taxonomy, collections).
*   **Concurrency & Task Management:** 
    *   Custom `TaskManager` (`task_manager.py`) using Python's `subprocess` and `threading` libraries.
    *   Manages background scripts (Scraper, Pipeline) via unbuffered execution (`python -u`).
    *   Relies on **Webhook updates** from background processes back to Flask (via `requests.post`) to update dashboard UI progress.
    *   Thread pools (`concurrent.futures.ThreadPoolExecutor`) used inside pipelines for simultaneous operations (e.g., Color extraction + Embeddings).

## 3. Database Layer
A highly optimized, embedded relational database approach.

*   **Core Engine:** **SQLite3** (`sqlite3` module). 
*   **Connection Configuration:** Uses `sqlite3.Row` for dictionary-like cursors. Crucially configures `PRAGMA journal_mode=WAL` (Write-Ahead Logging) to allow concurrent reads during background writes.
*   **Features & Optimization:**
    *   **Full-Text Search (FTS5)**: Dedicated virtual table (`items_fts`) with triggers (`AFTER INSERT / UPDATE / DELETE` on `items` table) to natively sync data for high-performance Porter-stemmed search.
    *   **Vector/Array Storage**: JSON serialization instead of strict array columns (e.g., storing Python lists as `BLOB` or `TEXT` inside `item_embeddings`).

## 4. AI & Data Pipeline
A robust ML/AI-enriched local workflow to semantically classify assets.

*   **Extraction & Scraping:** 
    *   `requests` / `cloudrequests` + `beautifulsoup4` for HTML parsing and auth (cookie-based bypasses for WP REST API).
    *   Custom checkpointing system (`checkpoints` table) allowing the scraper to resume interrupted downloads gracefully.
*   **AI Tagging (`ai_tagger.py`):** Uses **Ollama** locally (e.g., `minicpm-v` vision model) to inspect extracted images and yield highly contextual descriptive tags.
*   **Visual Similarity & Embeddings (`generate_embeddings.py`):** 
    *   **Ollama Embeddings**: Likely relying on text/multimodal embeddings locally. 
    *   **Cosine Similarity**: Done purely natively in Python math instead of using vector DBs (PGVector/Chroma) due to dataset scale ("Pure Vector Search" by looping over SQLite JSON embeddings).
    *   **Color Extraction (`extract_colors.py`)**: Uses local image parsing to yield HSL/Hex, matched into a custom deterministic taxonomy (`COLOR_FAMILIES`).
*   **Smart Orchestration (`process_assets.py`):** A pipeline tool executing operations based on `item` enrichment delta (partially enriched vs new), heavily guarded by thread locks and distinct SQLite connections for thread safety.

## 5. Summary & Anti-Collsion Strategies
When formulating an audit prompt for this stack, keep the following paradigms in mind:
*   **Zero-Build Frontend**: Avoid suggesting Node/npm/Webpack tools. All JS must remain browser-compatible ES6.
*   **Raw SQL over ORM**: Direct raw queries and schema definitions. Audits should focus on SQLite index optimization, manual triggers, and FTS tables instead of SQLAlchemy optimizations.
*   **Dependency Minimization**: The stack relies on native OS-level parallelism (`subprocess`, `threading`) over message brokers (Celery/Redis). Audits regarding scaling should respect the single-node, deeply local nature of this pipeline.
