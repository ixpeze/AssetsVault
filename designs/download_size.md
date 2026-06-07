# Design Documentation: Download File Size Integration

## Understanding Summary
- **Goal**: Show the download file size of 3D assets on item cards and in the lightbox details panel.
- **Data Source**: Pre-calculated and cached from Google Drive and mirror download links using a background script.
- **Target Audience**: Users browsing and downloading assets in the 3DSkyFree gallery.
- **Constraints**: SQLite database must handle concurrent access without throwing lock errors. Size checks must not slow down web page API requests.

## Decision Log
- **Decision 1**: Cache file sizes in `item_metadata` table instead of fetching them on-demand.
  - *Alternatives considered*: Fetch size dynamically via API requests during gallery page load.
  - *Rationale*: Pre-caching ensures gallery search remains sub-millisecond and avoids Cloudflare/Google rate limit bans.
- **Decision 2**: Handle SQLite busy locks using busy timeouts and exponential retry backoffs in the Python script.
  - *Alternatives considered*: Single-threaded serial updates or ignoring lock exceptions.
  - *Rationale*: WAL mode helps, but robust retries prevent scraper crashes when concurrent pipelines are running.
- **Decision 3**: Display the size inside the card category label as a bullet separator (`CATEGORY • SIZE`).
  - *Alternatives considered*: Adding a custom float badge over the image or custom columns in the card.
  - *Rationale*: Avoids visual clutter, keeps the UI extremely premium, and seamlessly scales across all grid card sizes (compact, responsive).

## Final Design

### 1. Database Queries & Lock Protection
- Connect to database with 30s timeout: `sqlite3.connect(db_path, timeout=30.0)`
- Execute `PRAGMA busy_timeout = 30000;` on all connections.
- Retries on write operations if a "database is locked" operational error occurs.
- Modify `backend/persistence/items.py` queries to LEFT JOIN `item_metadata` on `items.id = item_metadata.item_id`.

### 2. Size Scraper Script (`scrape_sizes.py`)
- Python script inside `scripts/pipeline/` querying items with GDrive/Mirror links missing sizes.
- Multi-threaded worker pool using `ThreadPoolExecutor` to probe remote sizes using lightweight stream request headers.
- Stores result bytes in `item_metadata.file_size`.

### 3. Frontend Updates
- **cards.js**: Export `formatBytes` helper, append formatted size (e.g. `24.5 MB`) to category name inside `buildCardHTML`.
- **index.html**: Add layout container `#lb-size-container` and text element `#lb-size` under the date field in the lightbox details panel.
- **dom.js**: Bind the elements.
- **lightbox.js**: Control visibility and value of size details when an item is clicked.
