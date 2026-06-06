# Obsidian Frost V2.2 — Design Document

> **Status:** Design Approved  
> **Date:** 2026-04-04  
> **Phases:** 3 (Power-User UX → Dashboard Intelligence → Visual Polish)

---

## Understanding Summary

- **What:** Three-phase upgrade to the 3DSkyFree gallery application — adding power-user keyboard navigation, URL deep-linking, improved search, batch download, a tabbed admin dashboard with scraper control and data quality tools, followed by visual polish
- **Why:** Transitioning from a personal tool to a public-facing product. At 85K items heading toward 1M+, the current UX and admin tools are insufficient for managing and discovering assets at scale
- **Who:** Primary — developer/admin (power user). Secondary — external visitors browsing 3D assets
- **Key Constraints:** Zero-build frontend (vanilla JS, no Node/Webpack), SQLite + FTS5, Tailwind CDN, no DCC bridges/3D viewer/star ratings, AI pipeline out of scope
- **Non-Goals:** Multi-user auth (this phase), AI enrichment improvements, mobile-first redesign

---

## Assumptions

| # | Assumption |
|---|---|
| A1 | Keyboard shortcuts include visual discoverability (`?` help overlay) since app is public-facing |
| A2 | Batch download = copy GDrive links to clipboard, not server-side zip |
| A3 | URL deep-linking uses query params (`?category=...`) not hash fragments |
| A4 | Dashboard/Admin is a single tabbed view, hidden from public users via `ADMIN_MODE` config flag |
| A5 | Force Rescrape uses smart upsert — updates item metadata, preserves all enrichment data (colors, tags, embeddings, favorites, collections) |
| A6 | All features must stay responsive at 1M items with SQLite |
| A7 | Deployment target is undecided — keep architecture portable (no cloud-specific dependencies) |
| A8 | `ADMIN_MODE` is an environment variable set in `start.bat`, not a login system |

---

## Decision Log

| # | Decision | Alternatives Considered | Rationale |
|---|---|---|---|
| D1 | **Phase order:** UX → Dashboard → Polish | Polish first, Dashboard first | UX features (deep-linking) are dependencies for Dashboard (click-to-filter in Data Quality tab) |
| D2 | **Progressive Enhancement Layer** for Phase 1 | Unified Interaction Manager, Web Components | Lowest risk, no regressions, respects zero-build constraint, fast to ship |
| D3 | **Single tabbed Dashboard** (not separate `/admin` route) | Separate `/admin` page, modal overlays, two admin pages | One entry point, one HTML template, one JS module. Cleaner than splitting admin across routes |
| D4 | **Dashboard hidden via `ADMIN_MODE` flag** | Login system, IP whitelist | Simple, no auth overhead, future-proofed for auth gating later |
| D5 | **Merge 3 bat files → 1 unified `start.bat`** | Keep separate files | Reduces confusion, single entry point with menu (Dev/Prod/Admin+Prod/Custom) |
| D6 | **Force Rescrape = smart UPDATE** (not INSERT OR REPLACE) | Delete and re-insert, full wipe | Preserves all enrichment data (colors, tags, embeddings, favorites, collections) |
| D7 | **Search grouped suggestions** (categories → tags → items) | Flat list, separate search modes | Better discoverability for 85K+ items, lets users jump to categories/tags directly |

---

## Phase 1 — Power-User UX

### 1.1 Keyboard Navigation
**New file:** `static/modules/keyboard.js`

**Gallery mode shortcuts:**

| Key | Action |
|---|---|
| `j` / `↓` | Move focus to next card |
| `k` / `↑` | Move focus to previous card |
| `h` / `←` | Move focus left in grid |
| `l` / `→` | Move focus right in grid |
| `Enter` / `Space` | Open focused card in lightbox |
| `f` | Toggle favorite on focused card |
| `x` | Toggle selection on focused card |
| `/` | Focus search (exists, preserve) |
| `?` | Show keyboard shortcut help overlay |
| `g g` | Scroll to top |
| `G` | Scroll to bottom / trigger infinite scroll |

**Visual feedback:** Focused card gets `ring-2 ring-primary/60` outline with `scrollIntoView({ block: 'nearest' })`.

**Help overlay:** Pressing `?` opens a modal listing all shortcuts. Dismissible with `Esc` or click-outside. Essential for public-facing discoverability.

**Integration:** Reads `state.items` for index tracking, calls existing `openLightboxWrap`, `toggleFavorite`, `toggleSelection`. No changes to existing modules.

---

### 1.2 URL Deep-Linking
**Extends:** `static/modules/search.js` (existing `pushStateToUrl` / `restoreStateFromUrl`)

**Query parameter mapping:**

| Param | State property | Example |
|---|---|---|
| `q` | `state.searchQuery` | `?q=leather+sofa` |
| `category` | `state.activeTaxonomy` | `?category=armchairs` |
| `tag` | `state.activeTag` | `?tag=modern` |
| `tags` | `state.activeTags` (multi) | `?tags=modern,wood&tags_mode=and` |
| `color` | `state.activeColor` | `?color=%23ff5500` |
| `tier` | `state.activeTier` | `?tier=free` |
| `sort` | `state.sortBy` | `?sort=title_asc` |
| `collection` | `state.activeCollection` | `?collection=5` |
| `fav` | `state.showFavorites` | `?fav=1` |
| `page` | `state.currentPage` | `?page=3` |
| `item` | lightbox open | `?item=12345` |

**Behavior:**
- Page load → parse params → hydrate state → single `fetchItems()` call
- Every filter change → `history.replaceState()` (no page reload)
- Back/forward → `popstate` listener re-hydrates and re-fetches
- `item` param replaces current `#item=` hash approach

---

### 1.3 Search-as-you-type Improvements
**Modifies:** `static/modules/search.js`

- Debounce reduced from 300ms → 150ms
- Abort controller cancels previous in-flight requests instantly (already exists)
- Autocomplete dropdown grouped: **Categories** → **Tags** → **Item titles**
- Matched characters bolded in dropdown for visual scanning

---

### 1.4 Batch Download
**Extends:** `static/modules/selection.js`

- New button in floating action bar: **"Copy Download Links"**
- Collects GDrive links from all selected items
- Copies newline-separated list to clipboard
- Toast notification: `"14 GDrive links copied (3 items had no link)"`
- No server-side processing

---

## Phase 2 — Dashboard Intelligence

### Architecture
Single tabbed admin panel at existing `/dashboard` route. Three tabs:

```
┌──────────┬──────────┬──────────────┐
│ Overview │ Scraper  │ Data Quality │
└──────────┴──────────┴──────────────┘
```

**Visibility:** Controlled by `ADMIN_MODE` environment variable.
- `ADMIN_MODE=1` → Dashboard link visible in sidebar
- `ADMIN_MODE=0` → Dashboard link hidden, `/dashboard` route returns 404

---

### 2.1 Overview Tab (Enhanced)
Existing dashboard content, reorganized:
- Stats cards stay, with **mini sparkline trends** (items over time from `collected_at`)
- Active tasks section with live log terminal
- New **Quick Actions** card: "Run Pipeline", "Recapture Links", "Vacuum DB", "Export Stats" in one row

---

### 2.2 Scraper Tab
**Category Tree Control Center:**
- Full hierarchical category tree (from `/api/taxonomy`)
- Each node shows: item count, last scraped date, status badge (✅/⚠️/❌)
- Per-node actions: `▶ Scrape` / `⏸ Resume` / `🔄 Force Rescrape`
- Active scrape shows live progress bar inline on the node
- Bulk actions bar: "Scrape All Unscraped" / "Resume All Partial"

**Force Rescrape behavior (Decision D6):**
- Existing items → `UPDATE` (preserves id, enrichment data stays intact)
- New items → `INSERT` (flagged as "needs enrichment")
- Never deletes colors, tags, embeddings, favorites, or collections

---

### 2.3 Data Quality Tab

**Tag Health Section:**
- Orphan tags (not attached to any item) — one-click bulk delete
- Near-duplicates (edit distance ≤ 2) — merge button
- Top 20 most/least used tags — histogram bars

**Missing Data Scorecard:**
- Per-category percentage bars: no image / no GDrive / no tags / no embeddings
- Click a bar → jumps to gallery with pre-applied filter (uses Phase 1 deep-linking)

**Bulk Actions:**
- "Delete all orphan tags" (with confirmation + count)
- "Re-extract colors for items missing colors"
- "Generate embeddings for unprocessed items"
- Each shows confirmation dialog before executing

---

## Phase 3 — Visual Polish (Deferred)
To be designed after Phases 1 & 2 are implemented. Focus areas:
- Consistent glassmorphism across all views (gallery + dashboard + admin)
- Micro-animations and transitions
- Theme system refinements
- Premium feel for public-facing gallery

---

## Implementation Order

```
Phase 1 — Power-User UX
├── 1.1 Keyboard Navigation (keyboard.js)
├── 1.2 URL Deep-Linking (extend search.js)
├── 1.3 Search Improvements (extend search.js)
└── 1.4 Batch Download (extend selection.js)

Phase 2 — Dashboard Intelligence
├── 2.0 ADMIN_MODE flag + unified start.bat
├── 2.1 Tab system + Overview enhancements
├── 2.2 Scraper Tab (category tree + smart rescrape)
└── 2.3 Data Quality Tab (tag health + missing data + bulk actions)

Phase 3 — Visual Polish
└── (Design TBD after Phase 1 & 2)
```

---

## Merged start.bat Menu

```
[1] Dev Mode      — FLASK_DEBUG=1, ADMIN_MODE=1, localhost:5000
[2] Production    — FLASK_DEBUG=0, ADMIN_MODE=0, localhost:5000 (public-safe)
[3] Admin + Prod  — FLASK_DEBUG=0, ADMIN_MODE=1, localhost:5000
[4] Custom Port   — prompt for port + settings
```

Old files to delete: `start-local.bat`, `start-remote.bat`

---

## Risks

| Risk | Mitigation |
|---|---|
| Keyboard nav conflicts with text input fields | Disable gallery shortcuts when any input/textarea is focused |
| SQLite performance at 1M items | FTS5 already handles this; add indexes for new query patterns as needed |
| Dashboard tab complexity creep | Each tab is a self-contained panel — no cross-tab state dependencies |
| Force rescrape data integrity | Transaction-wrapped UPDATE with rollback on error |
