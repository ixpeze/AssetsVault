# Roadmap — Obsidian Frost V3

This document captures deferred features, improvement ideas, and technical debt discovered during the V2.2 development cycle. Items are prioritized by user impact.

---

## High Priority

| Feature | Rationale |
|---------|-----------|
| **Grouped autocomplete suggestions** | Search suggestions currently show flat results. Grouping into Categories → Tags → Items with bold matched characters would significantly improve search UX. (Partially started in Phase 1.3) |
| **Exclude filters** (NOT this category, NOT this tag) | Power users frequently need negative filtering. Currently only inclusive filters exist. |
| **Nested collections** (folder hierarchy) | Collections are flat lists. A folder tree would enable much better organization for large libraries. |
| **Collection cover image** | Auto-pick the first item's image or let the user choose. Makes collection browsing much more visual. |
| **Drag-and-drop items between collections** | Currently requires removing + re-adding. Direct drag-and-drop would be faster. |
| **Per-category enrichment coverage heatmap** | Dashboard shows missing data counts per category, but a visual heatmap would make coverage gaps immediately obvious. |

---

## Medium Priority

| Feature | Rationale |
|---------|-----------|
| **Bulk tag editor** | Apply/remove tags to multiple selected items at once. The selection system (`x` to select) already exists, just needs a tag editor modal. |
| **AI-suggested related tags** | When editing tags in the lightbox, suggest related tags based on the item's existing tags and content. Requires Ollama. |
| **Smart collection sharing** | Export a collection as an image grid snapshot or shareable link. |
| **DB health monitor** | WAL checkpoint status, FTS index drift detection, orphan embedding cleanup. Some of this exists in Data Quality tab but could be expanded. |
| **Image download + local caching** | Download all asset images locally for offline browsing. Could run as a background pipeline task. |
| **Virtual scrolling** | Replace infinite scroll with a virtualized grid renderer to handle 85K+ items without DOM bloat. Would dramatically reduce memory usage. |

---

## Low Priority

| Feature | Rationale |
|---------|-----------|
| **High contrast theme** | Accessibility improvement. The current themes are dark-mode focused. |
| **Infinite scroll position memory** | When returning from lightbox, restore exact scroll position. Currently scrolls to approximate position. |
| **Export/import collections** | JSON export of collection data for backup or sharing between instances. |
| **Batch download as ZIP** | Download multiple selected items' GDrive links in one action. Complex due to external link nature. |
| **WebSocket live task updates** | Dashboard task monitor currently polls. WebSocket would give instant progress updates. |
| **Multi-user support** | Add user accounts with separate favorites/collections. Currently single-user only. |

---

## Technical Debt

| Item | Notes |
|------|-------|
| `init.js` is 920+ lines | Should be broken into smaller orchestration modules. Core fetch/render logic could move to dedicated modules. |
| `templates/index.html` contains all CSS | CSS should be extracted to separate `.css` files for maintainability. Currently ~800+ lines of inline CSS. |
| `find_page_with_count()` unused | Added for FTS-filtered queries where it's 1.5x faster, but search.py still uses separate queries. Could be selectively enabled for filtered requests only. |
| Test coverage is zero | No automated tests exist. Critical paths (search, pagination, tag CRUD) should have integration tests. |
| `app.js` is deprecated but still shipped | The legacy monolithic JS file should be removed once confirmed no references exist. |
| Scraper error handling | The scraper pipeline handles most errors gracefully but could benefit from retry logic with exponential backoff. |

---

## Explicitly Excluded from Roadmap

These were discussed during brainstorming and intentionally excluded:

| Feature | Reason |
|---------|--------|
| Bridge to DCC software (Blender, 3ds Max) | Out of scope — this is an asset browser, not an integration tool |
| 3D Model viewer | Would require WebGL/Three.js and model file downloads — too heavy |
| Keyboard command palette (Ctrl+K) | The native search box + `?` shortcut overlay is sufficient |
| Star rating (1-5) replacing binary favorite | Binary favorite is simpler and faster; ratings add UI complexity without clear benefit |
| AI & Enrichment pipeline features | Deferred indefinitely — local AI features are optional and depend on Ollama availability |
| Download & Integration features | GDrive links are external; automated download pipelines are out of scope |
