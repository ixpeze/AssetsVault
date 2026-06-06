// ── Obsidian Frost — Main Entry Point (ES Module) ──
// Imports all modules and wires up the application.

import { state, tagManagerState } from './state.js';
import { dom } from './dom.js';
import { apiGet, apiPost, apiDelete } from './api.js';
import { showToast } from './toast.js';
import { toggleSelection, clearSelection, updateSelectionUI, copySelectedLinks } from './selection.js';
import { toggleFavorite, fetchFavoriteIds, refreshVisibleFavStars, favoriteAllSelected } from './favorites.js';
import { fetchColors } from './colors.js';
import { renderTaxonomyTree, attachTaxonomyListeners } from './taxonomy.js';
import { applyFilters, applyGridScale, recalcColumns, setTierFilter, updateFooter, renderSkeleton } from './filters.js';
import { cleanTitle, buildCategoryTree, attachCardListeners, initCardDelegation } from './cards.js?v=4';
import { initVirtualGrid, setGridItems, clearGridDOM } from './grid.js?v=4';
import { checkClientDownloaderBootstrap, openDownloadsFolder, startActiveDownloadsMonitor } from './downloader.js?v=4';
import {
    buildItemParams, pushStateToUrl, restoreStateFromUrl, fetchStats,
    showAutocompleteSuggestions, hideAutocompleteSuggestions
} from './search.js';
import {
    openLightbox, closeLightbox, navigateLightbox,
    addTagToItem, loadLightboxSimilar, renderLightboxCollectionDropdown
} from './lightbox.js';
import {
    fetchCollections, renderCollections, openCollectionModal, closeCollectionModal,
    openCollectionPicker, closeCollectionPicker, renderCollectionPicker,
    bulkAddToCollection, fetchSmartCollections, renderSmartCollections,
    saveCurrentSearch as _saveCurrentSearch, importCollection as _importCollection
} from './collections.js';
import {
    fetchTags, renderTagCloud, clearTagFilter as _clearTagFilter,
    openTagManager, closeTagManager, updateTagManagerUI,
    mergeTags, _executeMerge, deleteTags, loadOrphanTags
} from './tags.js';
import {
    showDashboard, showGallery as _showGallery, updateDashboard as _updateDashboard,
    renderDashStats, fetchAnalytics, loadDbHealth, loadCoverageHeatmap,
    renderTaskTable, renderTaskLogs, updateTaskCardStatuses, selectTaskLog as _selectTaskLog,
    startTask as _startTask, stopTask as _stopTask, stopTaskByType as _stopTaskByType,
    clearCompletedTasks as _clearCompletedTasks,
    startPipeline as _startPipeline, startPipelineWithPrompt as _startPipelineWithPrompt,
    startRecapture as _startRecapture, startRecaptureWithPrompt as _startRecaptureWithPrompt
} from './dashboard.js';
import { initThumbnailObserver } from './thumbnails.js';
import { handleGalleryKey, focusCard, clearFocus, updateColumnCount, toggleHelpOverlay } from './keyboard.js';
import { initDashboardTabs, switchTab, resetTabCache } from './dashboard-tabs.js';

// ── Helper wrappers (bind showToast + other deps for cleaner calls) ──

function showGallery() { _showGallery(); }

const dashDeps = () => ({
    renderDashStats, renderTaskTable, renderTaskLogs, updateTaskCardStatuses
});

function updateDashboard() {
    _updateDashboard(dashDeps());
}

function setActiveTaxonomy(slug, name) {
    showGallery();
    state.activeTaxonomy = slug;
    state.activeCategory = "";
    dom.currentCategoryName.textContent = name || slug;
    fetchItems();
    renderTaxonomyTree();
    if (window.innerWidth < 768) dom.sidebar.classList.remove("open");
}

const lbDeps = () => ({
    cleanTitle, setActiveTaxonomy, fetchItems, showToast,
    closeLightbox: () => closeLightbox(lbDeps()),
    fetchMore
});

function openLightboxWrap(idx) {
    openLightbox(idx, lbDeps());
    preloadAdjacentImages(idx);
}
function closeLightboxWrap() { closeLightbox(lbDeps()); }

// ── Image preloader for smooth keyboard navigation ──
function preloadAdjacentImages(currentIndex) {
    [-1, 1, 2].forEach(offset => {
        const item = state.items[currentIndex + offset];
        if (!item) return;
        const src = item.local_image_url || item.image_url || '';
        if (!src) return;
        const img = new Image();
        img.src = src;
    });
}

const tagcloudDeps = () => ({
    showGallery, fetchItems,
    showToast,
    clearTagFilter: () => _clearTagFilter(tagcloudDeps()),
    renderTagCloud: () => renderTagCloud(tagcloudDeps()),
});

function renderTagCloudWrap() { renderTagCloud(tagcloudDeps()); }

const collDeps = () => ({
    showGallery, fetchItems, showToast,
    fetchCollections: (cb) => fetchCollections(cb || (() => renderCollections(collDeps()))),
    renderCollections: () => renderCollections(collDeps()),
    bulkAddToCollection: (id) => bulkAddToCollection(id, collDeps()),
    applySmartCollectionFilters,
});

function renderCollectionsWrap() { renderCollections(collDeps()); }

// ── fetchItems ──
let fetchItemsAbortController = null;

async function fetchItems() {
    if (state.loading) return;
    state.loading = true;
    state.currentPage = 1;
    state.allLoaded = false;
    dom.emptyState.classList.add("hidden");
    dom.scrollEnd.classList.add("hidden");
    
    const banner = document.getElementById("visual-search-banner");
    if (banner) banner.remove();
    
    clearGridDOM();
    renderSkeleton();

    if (fetchItemsAbortController) fetchItemsAbortController.abort();
    fetchItemsAbortController = new AbortController();

    try {
        const params = buildItemParams();
        const resp = await fetch(`/api/items?${params.toString()}`, { signal: fetchItemsAbortController.signal });
        const data = await resp.json();

        state.items = data.items || data;
        state.total = data.total || state.items.length;
        state.totalPages = data.pages || 1;
        state.currentPage = 1;
        state.allLoaded = state.items.length >= state.total;

        clearGridDOM();

        if (state.items.length === 0) {
            dom.emptyState.style.display = "";
        } else {
            dom.emptyState.style.display = "none";
            setGridItems(state.items);
        }

        updateFooter(state);
        pushStateToUrl();
        window.dispatchEvent(new Event('itemsFetched'));
        setTimeout(checkAndFillGrid, 100);
    } catch (e) {
        if (e.name !== 'AbortError') { console.error("fetchItems failed", e); showToast("Failed to load items", "error"); }
    } finally {
        state.loading = false;
        dom.scrollLoader.classList.add("hidden");
    }
}

let _fillGridPending = false;
function checkAndFillGrid() {
    if (_fillGridPending || state.loading || state.loadingMore || state.allLoaded) return;
    if (!dom.scrollSentinel) return;

    const rect = dom.scrollSentinel.getBoundingClientRect();
    const isVisible = rect.top < window.innerHeight;

    if (isVisible) {
        _fillGridPending = true;
        fetchMore().finally(() => { _fillGridPending = false; });
    }
}

async function fetchMore() {
    if (state.loadingMore || state.allLoaded || state.loading) return;
    state.loadingMore = true;
    dom.scrollLoader.classList.remove("hidden");
    try {
        state.currentPage++;
        const params = buildItemParams();
        const resp = await fetch(`/api/items?${params.toString()}`);
        const data = await resp.json();
        const newItems = data.items || data;

        if (!newItems.length) { state.allLoaded = true; dom.scrollEnd.classList.remove("hidden"); return; }

        state.items.push(...newItems);
        state.allLoaded = state.items.length >= state.total;

        setGridItems(state.items);
        updateFooter(state);
        if (state.allLoaded) { dom.scrollEnd.classList.remove("hidden"); dom.scrollLoader.classList.add("hidden"); }
        setTimeout(checkAndFillGrid, 100);
    } catch (e) { console.error("fetchMore failed", e); state.currentPage--; }
    finally { state.loadingMore = false; dom.scrollLoader.classList.add("hidden"); }
}

// ── Infinite scroll observer ──
const scrollObserver = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !state.allLoaded && !state.loading && !state.loadingMore) {
        fetchMore();
    }
}, { threshold: 0.1 });
if (dom.scrollSentinel) scrollObserver.observe(dom.scrollSentinel);

// ── Smart Grid: recalculate columns whenever the scroll container resizes ──
// This covers: focus mode toggle, sidebar collapse, window resize.
let _resizeRafId = null;
const _gridResizer = new ResizeObserver(() => {
    if (_resizeRafId) cancelAnimationFrame(_resizeRafId);
    _resizeRafId = requestAnimationFrame(() => {
        recalcColumns();
        _resizeRafId = null;
    });
});
if (dom.scrollContainer) _gridResizer.observe(dom.scrollContainer);

// ── Category fetching ──
async function fetchCategories() {
    try {
        const cats = await apiGet("/api/categories");
        state.categories = Array.isArray(cats) ? cats : (cats.categories || []);
        state.categoryTree = buildCategoryTree(state.categories);
        state.taxonomyTree = await apiGet("/api/taxonomy").catch(() => state.categoryTree);
        renderTaxonomyTree();
        attachTaxonomyListeners(setActiveTaxonomy);
        updateCategoryCountBadges();
    } catch (e) { console.error("Failed to fetch categories", e); }
}

function updateCategoryCountBadges() {
    if (!state.categories || !state.categories.length) return;
    document.querySelectorAll('.category-item[data-slug]').forEach(el => {
        const slug = el.dataset.slug;
        if (!slug) return;
        const cat = state.categories.find(c => c.slug === slug || c.name === slug);
        if (!cat) return;
        const count = cat.count || cat.item_count || 0;
        if (!count) return;
        let badge = el.querySelector('.cat-count-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'cat-count-badge ml-auto text-[9px] text-text-muted bg-[#151515] px-1 rounded tabular-nums';
            el.appendChild(badge);
        }
        badge.textContent = count >= 1000 ? `${(count / 1000).toFixed(1)}k` : count;
    });
}

// ── Context menu ──
function showContextMenu(x, y) {
    const isFav = state.favoriteIds.has(state.contextItemId);
    dom.ctxFavorite.textContent = isFav ? "Remove Favorite" : "Add to Favorites";
    dom.contextMenu.style.left = `${x}px`;
    dom.contextMenu.style.top = `${y}px`;
    dom.contextMenu.classList.remove("hidden");
}

document.addEventListener("click", () => dom.contextMenu.classList.add("hidden"));
if (dom.ctxFavorite) {
    dom.ctxFavorite.addEventListener("click", async () => {
        await toggleFavorite(state.contextItemId);
        refreshVisibleFavStars();
    });
}
if (dom.ctxCollections) {
    dom.ctxCollections.addEventListener("click", () => {
        const prev = state.selectedIds;
        state.selectedIds = new Set([state.contextItemId]);
        openCollectionPicker(showToast, () => renderCollectionPicker(collDeps()));
        state.selectedIds = prev;
    });
}
if (dom.ctxNewCollection) {
    dom.ctxNewCollection.addEventListener("click", () => openCollectionModal(true, collDeps()));
}

// ── Sidebar & Gallery show/hide ──
function showGalleryAndReset() {
    showGallery();
    state.showFavorites = false;
    state.activeCollection = null;
    dom.allAssetsLink.classList.add("bg-frost-hover", "text-white");
    dom.favoritesLink.classList.remove("bg-frost-hover", "text-white");
}

if (dom.allAssetsLink) {
    dom.allAssetsLink.addEventListener("click", (e) => {
        e.preventDefault();
        showGalleryAndReset();
        state.activeCategory = "";
        state.activeTaxonomy = "";
        dom.currentCategoryName.textContent = "All Assets";
        fetchItems();
        renderTaxonomyTree();
    });
}

if (dom.favoritesLink) {
    dom.favoritesLink.addEventListener("click", (e) => {
        e.preventDefault();
        showGallery();
        state.showFavorites = !state.showFavorites;
        dom.favoritesLink.classList.toggle("bg-frost-hover", state.showFavorites);
        dom.favoritesLink.classList.toggle("text-white", state.showFavorites);
        dom.allAssetsLink.classList.toggle("bg-frost-hover", !state.showFavorites);
        dom.currentCategoryName.textContent = state.showFavorites ? "★ Favorites" : "All Assets";
        fetchItems();
    });
}

if (dom.dashboardLink) {
    dom.dashboardLink.addEventListener("click", (e) => {
        e.preventDefault();
        const deps = { updateDashboard, fetchAnalytics, loadDbHealth, loadCoverageHeatmap };
        showDashboard(deps);
        // Init tabs once dashboard is shown
        initDashboardTabs(deps);
    });
}

document.getElementById('open-downloads-folder')?.addEventListener('click', openDownloadsFolder);

// ── Search ──
let searchTimer;
let autocompleteTimer;
if (dom.searchInput) {
    dom.searchInput.addEventListener("input", (e) => {
        const val = e.target.value;
        state.searchQuery = val;
        dom.searchClear.classList.toggle("hidden", !val);
        clearTimeout(searchTimer);
        clearTimeout(autocompleteTimer);
        if (val.length > 1) {
            autocompleteTimer = setTimeout(() => showAutocompleteSuggestions(val, setActiveTaxonomy), 250);
        } else {
            hideAutocompleteSuggestions();
        }
        searchTimer = setTimeout(fetchItems, 200);
    });
    dom.searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { clearTimeout(searchTimer); hideAutocompleteSuggestions(); fetchItems(); }
        if (e.key === "Escape") { dom.searchInput.value = ""; state.searchQuery = ""; dom.searchClear.classList.add("hidden"); hideAutocompleteSuggestions(); fetchItems(); }
    });
}
if (dom.searchClear) {
    dom.searchClear.addEventListener("click", () => {
        dom.searchInput.value = ""; state.searchQuery = ""; dom.searchClear.classList.add("hidden"); hideAutocompleteSuggestions(); fetchItems();
    });
}

// ── Advanced Filters ──
document.getElementById("filters-toggle")?.addEventListener("click", () => {
    document.getElementById("filters-panel")?.classList.toggle("hidden");
});

// Wire filter dropdowns to the imported applyFilters from filters.js
["filter-gdrive", "filter-image", "filter-tier"].forEach(id => {
    document.getElementById(id)?.addEventListener("change", () => applyFilters(fetchItems));
});

const filtersClear = document.getElementById("filters-clear");
if (filtersClear) {
    filtersClear.addEventListener("click", () => {
        Object.keys(state.advancedFilters).forEach(k => state.advancedFilters[k] = "");
        ["filter-gdrive", "filter-image", "filter-tier"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
        const badge = document.getElementById("active-filters-badge");
        if (badge) badge.classList.add("hidden");
        filtersClear.classList.add("hidden");
        fetchItems();
    });
}

// ── Sort select ──
if (dom.sortSelect) {
    dom.sortSelect.addEventListener("change", (e) => { state.sortBy = e.target.value; fetchItems(); });
}

// ── Grid scale ──
const savedScale = localStorage.getItem("gridScale") || "1";
applyGridScale(savedScale);
if (dom.gridScale) {
    dom.gridScale.addEventListener("input", (e) => applyGridScale(e.target.value));
}
document.querySelectorAll(".grid-preset").forEach(btn => {
    btn.addEventListener("click", () => {
        dom.gridScale.value = btn.dataset.scale;
        applyGridScale(btn.dataset.scale);
        localStorage.setItem("gridScale", btn.dataset.scale);
    });
});

// ── Tier filter ──
if (dom.pillAll) dom.pillAll.addEventListener("click", () => setTierFilter("", rebuildFilteredTree, fetchItems));
if (dom.pillFree) dom.pillFree.addEventListener("click", () => setTierFilter("Free", rebuildFilteredTree, fetchItems));
if (dom.pillPaid) dom.pillPaid.addEventListener("click", () => setTierFilter("Paid", rebuildFilteredTree, fetchItems));

function rebuildFilteredTree() { renderTaxonomyTree(); attachTaxonomyListeners(setActiveTaxonomy); }

// ── Keyboard shortcuts ──
document.addEventListener("keydown", (e) => {
    // '?' help overlay — handled inside keyboard module (works in all contexts)
    if (e.key === '?' && !e.ctrlKey && !e.metaKey) { toggleHelpOverlay(); return; }

    const activeTag = document.activeElement.tagName;
    const isEditable = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT"
        || document.activeElement.isContentEditable;

    // Lightbox mode
    if (state.lightboxIndex >= 0) {
        if (isEditable) return;
        if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigateLightbox(-1, lbDeps()); }
        if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigateLightbox(1, lbDeps()); }
        if (e.key === "Escape") closeLightboxWrap();
        if (e.key === "f" || e.key === "F") toggleFavorite(state.items[state.lightboxIndex]?.id).then(refreshVisibleFavStars);
        return;
    }

    // Global shortcuts (work even in inputs)
    if (e.key === "/" || (e.key === "k" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); dom.searchInput.focus(); dom.searchInput.select(); return; }
    if (e.key === "F2") { toggleFocusMode(); return; }
    if (e.key === "Escape") { clearSelection(); updateSelectionUI(); return; }
    if (e.key === "a" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); state.items.forEach(i => state.selectedIds.add(i.id)); updateSelectionUI(); return; }

    // Gallery keyboard navigation (skip if typing)
    if (!isEditable) {
        handleGalleryKey(e, {
            openLightbox: openLightboxWrap,
            toggleFavorite: (id) => toggleFavorite(id).then(refreshVisibleFavStars),
            toggleSelection,
            updateSelectionUI,
        });
    }
});

// Clear keyboard focus when new items load
window.addEventListener('itemsFetched', () => { clearFocus(); setTimeout(updateColumnCount, 100); });
window.addEventListener('resize', updateColumnCount);

// ── Lightbox event listeners ──
if (dom.lbClose) dom.lbClose.addEventListener("click", closeLightboxWrap);
if (dom.lbBackdrop) dom.lbBackdrop.addEventListener("click", closeLightboxWrap);
if (dom.lbPrev) dom.lbPrev.addEventListener("click", () => navigateLightbox(-1, lbDeps()));
if (dom.lbNext) dom.lbNext.addEventListener("click", () => navigateLightbox(1, lbDeps()));

// Swipe support
let touchStartX = 0;
document.addEventListener('touchstart', (e) => { touchStartX = e.changedTouches[0].screenX; }, { passive: true });
document.addEventListener('touchend', (e) => {
    if (state.lightboxIndex < 0) return;
    const dx = e.changedTouches[0].screenX - touchStartX;
    if (Math.abs(dx) > 50) navigateLightbox(dx < 0 ? 1 : -1, lbDeps());
}, { passive: true });

// ── Lightbox tag input ──
const lbTagInput = document.getElementById('lb-tag-input');
const lbTagAddBtn = document.getElementById('lb-tag-add');

function submitLightboxTag() {
    const tag = lbTagInput?.value.trim().toLowerCase();
    if (!tag) return;
    const item = state.items[state.lightboxIndex];
    if (item) addTagToItem(item.id, tag, lbDeps()).then(() => { if (lbTagInput) lbTagInput.value = ''; });
}

if (lbTagInput) {
    lbTagInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); submitLightboxTag(); }
    });
}
if (lbTagAddBtn) {
    lbTagAddBtn.addEventListener('click', submitLightboxTag);
}

// ── Sidebar toggle (mobile) ──
if (dom.sidebarToggle) dom.sidebarToggle.addEventListener("click", () => dom.sidebar.classList.add("open"));
if (dom.sidebarClose) dom.sidebarClose.addEventListener("click", () => dom.sidebar.classList.remove("open"));

// ── Collection modal & picker ──
if (dom.newCollectionBtn) dom.newCollectionBtn.addEventListener("click", () => openCollectionModal(false, collDeps()));
if (dom.modalCancel) dom.modalCancel.addEventListener("click", closeCollectionModal);
if (dom.modalBackdrop) dom.modalBackdrop.addEventListener("click", closeCollectionModal);
if (dom.pickerCancel) dom.pickerCancel.addEventListener("click", closeCollectionPicker);
if (dom.pickerBackdrop) dom.pickerBackdrop.addEventListener("click", closeCollectionPicker);

// ── Action bar ──
if (dom.actionCopy) dom.actionCopy.addEventListener("click", () => copySelectedLinks(showToast));
if (dom.actionFav) dom.actionFav.addEventListener("click", () => favoriteAllSelected(showToast).then(refreshVisibleFavStars));
if (dom.actionCollection) dom.actionCollection.addEventListener("click", () => openCollectionPicker(showToast, () => renderCollectionPicker(collDeps())));
if (dom.actionClear) dom.actionClear.addEventListener("click", () => { clearSelection(); updateSelectionUI(); });

// ── Tag Manager ──
if (dom.manageTagsBtn) {
    dom.manageTagsBtn.addEventListener("click", () => {
        openTagManager();
        setTimeout(() => loadOrphanTags(showToast, () => fetchTags(renderTagCloudWrap)), 600);
    });
}
if (dom.tagManagerBackdrop) dom.tagManagerBackdrop.addEventListener("click", closeTagManager);
if (dom.tagManagerClose) dom.tagManagerClose.addEventListener("click", closeTagManager);
if (dom.tagSearch) {
    dom.tagSearch.addEventListener("input", () => {
        const q = dom.tagSearch.value.toLowerCase();
        tagManagerState.filteredTags = tagManagerState.allTags.filter(t => t.name.toLowerCase().includes(q));
        import('./tags.js').then(m => m.renderTagManager());
    });
}
if (dom.tagSelectAll) {
    dom.tagSelectAll.addEventListener("click", () => {
        tagManagerState.filteredTags.forEach(t => tagManagerState.selectedTagIds.add(t.id));
        updateTagManagerUI();
    });
}
if (dom.tagDeselectAll) {
    dom.tagDeselectAll.addEventListener("click", () => {
        tagManagerState.selectedTagIds.clear();
        updateTagManagerUI();
    });
}
if (dom.tagMergeBtn) dom.tagMergeBtn.addEventListener("click", () => mergeTags(showToast));
if (dom.tagDeleteBtn) dom.tagDeleteBtn.addEventListener("click", () => deleteTags(showToast, () => fetchTags(renderTagCloudWrap)));

// IDs in HTML are merge-confirm-btn and merge-cancel-btn
const mergeConfirmBtn = document.getElementById('merge-confirm-btn');
const mergeCancelBtn = document.getElementById('merge-cancel-btn');
if (mergeConfirmBtn) {
    mergeConfirmBtn.addEventListener('click', () => {
        const targetInput = document.getElementById('merge-target-input');
        if (targetInput) _executeMerge(targetInput.value, showToast, () => fetchTags(renderTagCloudWrap));
    });
}
if (mergeCancelBtn) mergeCancelBtn.addEventListener('click', () => document.getElementById('merge-dialog')?.classList.add('hidden'));

// ── Theme picker ──
const THEMES = {
    "": { label: "Obsidian Frost" }, "highcontrast": { label: "High Contrast" },
    "silver-charcoal": { label: "Silver Charcoal" }, "cmyk": { label: "CMYK" },
    "github-dark": { label: "GitHub Style" }, "glass-dark": { label: "Glass Dark" },
    "glass-light": { label: "Glass Light" }, "flat-dark": { label: "Flat Dark" },
    "flat-light": { label: "Flat Light" }, "macos-sequoia": { label: "macOS Sequoia" },
    "obsidian": { label: "✦ Obsidian" }, "aurora": { label: "✦ Aurora" },
};
let activeTheme = localStorage.getItem('activeTheme') || '';

function applyTheme(theme) {
    activeTheme = theme;
    if (theme) document.documentElement.setAttribute('data-theme', theme);
    else document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('activeTheme', theme);
    document.querySelectorAll('.theme-option').forEach(btn => btn.classList.toggle('active', btn.dataset.theme === theme));
}
applyTheme(activeTheme);

const themeBtn = document.getElementById('theme-btn');
const themeMenu = document.getElementById('theme-menu');
if (themeBtn && themeMenu) {
    themeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const rect = themeBtn.getBoundingClientRect();
        themeMenu.style.top = (rect.bottom + 4) + 'px';
        themeMenu.style.right = (window.innerWidth - rect.right) + 'px';
        themeMenu.style.left = 'auto';
        themeMenu.classList.toggle('hidden');
    });
    themeMenu.querySelectorAll('.theme-option').forEach(opt => {
        opt.addEventListener('click', (e) => { e.stopPropagation(); applyTheme(opt.dataset.theme); themeMenu.classList.add('hidden'); showToast(`Theme: ${THEMES[opt.dataset.theme]?.label || 'Default'}`); });
    });
    document.addEventListener('click', (e) => { if (!themeMenu.contains(e.target) && e.target !== themeBtn) themeMenu.classList.add('hidden'); });
}

// ── Compact mode ──
let compactMode = localStorage.getItem('compactMode') === '1';
function applyCompactMode() {
    document.body.classList.toggle('compact-mode', compactMode);
    const btn = document.getElementById('compact-toggle');
    if (btn) { btn.classList.toggle('text-primary', compactMode); btn.classList.toggle('text-text-muted', !compactMode); }
}
const compactToggleBtn = document.getElementById('compact-toggle');
if (compactToggleBtn) {
    compactToggleBtn.addEventListener('click', () => {
        compactMode = !compactMode;
        localStorage.setItem('compactMode', compactMode ? '1' : '0');
        applyCompactMode();
        showToast(compactMode ? 'Compact mode ON' : 'Compact mode OFF');
    });
}
applyCompactMode();

// ── Focus mode ──
(function injectFocusModeStyles() {
    const s = document.createElement('style');
    s.textContent = `
        body.focus-mode aside#sidebar         { display: none !important; }
        body.focus-mode #main-toolbar         { display: none !important; }
        body.focus-mode #main-search-bar      { display: none !important; }
        body.focus-mode #focus-mode-btn       { display: none !important; }
        body.focus-mode #focus-hud            { display: block !important; }
        body.focus-mode #focus-exit-btn       { display: flex !important; }
        body.focus-mode #focus-tags-bar       { display: flex !important; }
        body.focus-mode #scroll-container     { padding-top: 7rem !important; padding-bottom: 5.5rem !important; }
        body.focus-mode #advanced-filters-bar {
            position: fixed !important; top: 0; left: 0; right: 0; z-index: 9985;
            display: block !important;
            background: rgba(5,5,5,0.97);
            backdrop-filter: blur(16px);
            border-bottom: 1px solid rgba(255,255,255,0.09);
        }
        body.focus-mode #advanced-filters-bar #filters-toggle-row { display: none !important; }
        body.focus-mode #advanced-filters-bar #filters-panel {
            display: block !important;
            padding: 0.35rem 1.25rem !important;
        }
        body.focus-mode #advanced-filters-bar #filters-panel label { display: none !important; }
        body.focus-mode #advanced-filters-bar #filters-panel .grid {
            grid-template-columns: repeat(4, auto);
            gap: 0.5rem !important;
            align-items: center;
            justify-content: start;
        }
        body.focus-mode #advanced-filters-bar #filters-panel select {
            padding-top: 0.15rem !important;
            padding-bottom: 0.15rem !important;
            font-size: 11px !important;
        }
        body.focus-mode .focus-hud-top { top: 3.1rem !important; }
        #focus-tags-bar::-webkit-scrollbar { display: none; }
    `;
    document.head.appendChild(s);
})();

function toggleFocusMode() {
    state.focusMode = !state.focusMode;
    localStorage.setItem('focusMode', state.focusMode ? '1' : '0');
    document.getElementById('advanced-filters-bar')?.classList.remove('focus-float');
    document.body.classList.toggle('focus-mode', state.focusMode);
    if (state.focusMode) syncFocusHud();
    showToast(state.focusMode ? 'Focus mode ON — press F2 to exit' : 'Focus mode OFF');
}

function syncFocusHud() {
    const focusSearch = document.getElementById('focus-search-input');
    if (focusSearch) focusSearch.value = dom.searchInput.value;
    const focusSlider = document.getElementById('focus-grid-scale');
    if (focusSlider) focusSlider.value = dom.gridScale.value;
    const focusSort = document.getElementById('focus-sort-select');
    if (focusSort) focusSort.value = state.sortBy || 'newest';
    applyGridScale(dom.gridScale.value);
}

if (state.focusMode) { document.body.classList.add('focus-mode'); syncFocusHud(); }

const focusBtn = document.getElementById('focus-mode-btn');
const focusExitBtn = document.getElementById('focus-exit-btn');
if (focusBtn) focusBtn.addEventListener('click', toggleFocusMode);
if (focusExitBtn) focusExitBtn.addEventListener('click', toggleFocusMode);

const focusSearchInput = document.getElementById('focus-search-input');
if (focusSearchInput) {
    let focusSearchTimer;
    focusSearchInput.addEventListener('input', (e) => {
        dom.searchInput.value = e.target.value;
        state.searchQuery = e.target.value;
        dom.searchClear.classList.toggle('hidden', !e.target.value);
        clearTimeout(focusSearchTimer);
        focusSearchTimer = setTimeout(fetchItems, 300);
    });
    focusSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { clearTimeout(focusSearchTimer); fetchItems(); }
        if (e.key === 'Escape') toggleFocusMode();
    });
}

const focusGridSlider = document.getElementById('focus-grid-scale');
if (focusGridSlider) focusGridSlider.addEventListener('input', (e) => applyGridScale(e.target.value));

const focusSortSel = document.getElementById('focus-sort-select');
if (focusSortSel) focusSortSel.addEventListener('change', (e) => { state.sortBy = e.target.value; dom.sortSelect.value = e.target.value; fetchItems(); });

const focusCatPill = document.getElementById('focus-cat');
if (focusCatPill) focusCatPill.addEventListener('click', clearAllFilters);

// ── Clear all filters ──
function clearAllFilters() {
    state.searchQuery = ""; state.activeTag = ""; state.activeTaxonomy = ""; state.activeCategory = "";
    state.activeColor = ""; state.activeTier = ""; state.showFavorites = false;
    state.showUntagged = false; state.activeCollection = null;
    dom.searchInput.value = ""; dom.searchClear.classList.add("hidden");
    dom.activeTagFilter.classList.add("hidden");
    dom.currentCategoryName.textContent = "All Assets";
    dom.allAssetsLink.classList.add("bg-frost-hover", "text-white");
    dom.favoritesLink.classList.remove("bg-frost-hover", "text-white");
    Object.keys(state.advancedFilters).forEach(k => state.advancedFilters[k] = "");
    ["filter-gdrive", "filter-image", "filter-tier"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    const badge = document.getElementById("active-filters-badge");
    const clearBtn = document.getElementById("filters-clear");
    if (badge) badge.classList.add("hidden");
    if (clearBtn) clearBtn.classList.add("hidden");
    updateGlobalClearPill();
    renderTaxonomyTree();
    fetchItems();
    showToast("All filters cleared");
}

function updateGlobalClearPill() {
    const pill = document.getElementById('global-clear-filters');
    if (!pill) return;
    const hasAny = state.searchQuery || state.activeTag || state.activeTaxonomy || state.activeCategory ||
        state.activeColor || state.activeTier || state.showFavorites || state.activeCollection ||
        Object.values(state.advancedFilters).some(v => v);
    pill.classList.toggle('hidden', !hasAny);
}

const globalClear = document.getElementById('global-clear-filters');
if (globalClear) globalClear.addEventListener('click', clearAllFilters);
window.addEventListener('itemsFetched', updateGlobalClearPill);

// ── Smart collections filter applier ──
function applySmartCollectionFilters(filters) {
    showGallery();
    state.searchQuery = filters.q || "";
    state.activeCategory = filters.category || "";
    state.activeTier = filters.tier || "";
    state.activeTag = filters.tag || "";
    state.activeColor = filters.color || "";
    state.showFavorites = filters.fav === "1";
    state.advancedFilters.hasGdrive = filters.hasGdrive || "";
    dom.searchInput.value = state.searchQuery;
    fetchItems();
}

// ── Sidebar stats ──
async function fetchSidebarStats() {
    try {
        const data = await apiGet('/api/counts');
        const uc = document.getElementById('stat-untagged-count');
        const mc = document.getElementById('stat-missing-count');
        if (uc) uc.textContent = data.untagged ?? '?';
        if (mc) mc.textContent = data.missing ?? '?';
    } catch (e) { /* optional */ }
}

// ── Clear tag filter link ──
if (dom.clearTagFilter) dom.clearTagFilter.addEventListener("click", () => _clearTagFilter(tagcloudDeps()));

// ── Lightbox collection picker & share ──
const lbCollect = document.getElementById('lb-add-collection');
const lbDropdown = document.getElementById('lb-collection-dropdown');
if (lbCollect && lbDropdown) {
    lbCollect.addEventListener('click', (e) => {
        e.stopPropagation();
        renderLightboxCollectionDropdown(() => fetchCollections(renderCollectionsWrap), showToast);
        lbDropdown.classList.toggle('hidden');
    });
    document.addEventListener('click', (e) => {
        if (!lbCollect.contains(e.target) && !lbDropdown.contains(e.target)) lbDropdown.classList.add('hidden');
    });
}

const lbShare = document.getElementById('lb-share');
if (lbShare) {
    lbShare.onclick = () => {
        const item = state.items[state.lightboxIndex];
        if (!item) return;
        const url = `${location.origin}${location.pathname}#item=${item.id}`;
        navigator.clipboard.writeText(url).then(() => showToast('Link copied!', 'success'));
    };
}

const btnSimilar = document.getElementById("lb-find-similar");
if (btnSimilar) {
    btnSimilar.onclick = () => {
        const item = state.items[state.lightboxIndex];
        if (item) loadLightboxSimilar(item.id, lbDeps());
    };
}

// ── Visual Search button in lightbox ──
const lbVisualSearchBtn = document.getElementById('lb-visual-search');
if (lbVisualSearchBtn) {
    lbVisualSearchBtn.addEventListener('click', () => {
        const item = state.items[state.lightboxIndex];
        if (item) window.visualSearch(item.id);
    });
}

const scrollTopBtn = document.getElementById('scroll-to-top');
if (scrollTopBtn && dom.scrollContainer) {
    dom.scrollContainer.addEventListener('scroll', () => scrollTopBtn.classList.toggle('hidden', dom.scrollContainer.scrollTop < 500));
    scrollTopBtn.addEventListener('click', () => dom.scrollContainer.scrollTo({ top: 0, behavior: 'smooth' }));
}

// Quick views collapsible panel
(function initQuickViews() {
    const btn = document.getElementById('quick-views-toggle');
    const panel = document.getElementById('quick-views-panel');
    const chevron = document.getElementById('quick-views-chevron');
    if (!btn || !panel) return;
    const open = localStorage.getItem('quickViewsOpen') === '1';
    if (open) { panel.classList.remove('hidden'); if (chevron) chevron.style.transform = 'rotate(90deg)'; }
    btn.addEventListener('click', () => {
        const isOpen = !panel.classList.contains('hidden');
        panel.classList.toggle('hidden', isOpen);
        if (chevron) chevron.style.transform = isOpen ? '' : 'rotate(90deg)';
        localStorage.setItem('quickViewsOpen', isOpen ? '0' : '1');
    });
})();

// Tag density slider
const densitySlider = document.getElementById('tag-density');
const densityVal = document.getElementById('tag-density-val');
if (densitySlider) {
    densitySlider.value = state.tagDensity;
    if (densityVal) densityVal.textContent = state.tagDensity;
    densitySlider.addEventListener('input', () => {
        state.tagDensity = parseInt(densitySlider.value);
        if (densityVal) densityVal.textContent = state.tagDensity;
        localStorage.setItem('tagDensity', state.tagDensity);
        renderTagCloudWrap();
    });
}

// Tag AND/OR mode
function updateTagModeToggle() {
    const btn = document.getElementById('tag-mode-toggle');
    const lbl = document.getElementById('tag-mode-label');
    if (!btn || !lbl) return;
    lbl.textContent = state.tagMode;
    btn.classList.toggle('text-primary', state.tagMode === 'OR');
    btn.classList.toggle('text-text-muted', state.tagMode === 'AND');
    const hasTag = !!state.activeTag;
    btn.classList.toggle('hidden', !hasTag); btn.classList.toggle('flex', hasTag);
}
const tagModeBtn = document.getElementById('tag-mode-toggle');
if (tagModeBtn) {
    tagModeBtn.addEventListener('click', () => {
        state.tagMode = state.tagMode === 'AND' ? 'OR' : 'AND';
        localStorage.setItem('tagMode', state.tagMode);
        updateTagModeToggle();
        showToast(`Tag filter mode: ${state.tagMode}`);
        fetchItems();
    });
}
updateTagModeToggle();

// Expose globals for inline HTML onclick handlers
window.stopTask = (id) => _stopTask(id, showToast, updateDashboard);
window.stopTaskByType = (type) => _stopTaskByType(type, showToast, updateDashboard);
window.startTask = (type, args) => _startTask(type, args, showToast, updateDashboard);
window.selectTaskLog = (id) => _selectTaskLog(id, updateDashboard);
window.clearCompletedTasks = () => _clearCompletedTasks(showToast, updateDashboard);
window.startPipeline = (args) => _startPipeline(args, showToast, updateDashboard);
window.startPipelineWithPrompt = () => _startPipelineWithPrompt(showToast, updateDashboard);
window.startRecapture = (args) => _startRecapture(args, showToast, updateDashboard);
window.startRecaptureWithPrompt = () => _startRecaptureWithPrompt(showToast, updateDashboard);
window.importCollection = () => _importCollection(showToast, () => fetchCollections(renderCollectionsWrap), renderCollectionsWrap);
window.saveCurrentSearch = () => _saveCurrentSearch(showToast, () => fetchSmartCollections(() => renderSmartCollections(collDeps())));
window.searchWithColor = (hex) => { state.activeColor = hex; fetchItems(); }; // for any legacy inline calls
window.visualSearch = async (itemId) => {
    closeLightboxWrap();
    state.loading = true;
    clearGridDOM(); renderSkeleton();
    try {
        const items = await apiGet(`/api/visual-search/${itemId}`);
        state.items = items; state.total = items.length; state.totalPages = 1; state.allLoaded = true;
        clearGridDOM();
        
        const banner = document.getElementById("visual-search-banner");
        if (banner) banner.remove();
        
        const header = document.createElement("div");
        header.id = "visual-search-banner";
        header.className = "p-4 mb-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-center justify-between";
        header.innerHTML = `<div class="flex items-center gap-2 text-emerald-200"><span class="material-symbols-outlined">image_search</span><span class="font-medium">Visually similar items</span></div><button id="clear-visual-search" class="text-xs bg-white/10 hover:bg-white/20 px-3 py-1 rounded text-white transition-colors">Clear</button>`;
        dom.grid.parentElement.insertBefore(header, dom.grid);
        document.getElementById("clear-visual-search").onclick = fetchItems;
        
        setGridItems(items);
        updateFooter(state);
    } catch (e) { showToast("Visual search failed - embeddings may not be generated"); fetchItems(); }
    finally { state.loading = false; dom.scrollLoader.classList.add("hidden"); }
};

// ── Init ──
function runWhenIdle(fn) {
    if ('requestIdleCallback' in window) {
        window.requestIdleCallback(fn, { timeout: 1500 });
    } else {
        setTimeout(fn, 250);
    }
}

async function init() {
    initThumbnailObserver();
    initVirtualGrid();
    startActiveDownloadsMonitor();
    initCardDelegation({
        openLightbox: openLightboxWrap,
        toggleSelection,
        toggleFavorite,
        showContextMenu,
    });
    const pendingItemId = restoreStateFromUrl();
    await Promise.all([
        fetchStats(),
        fetchCategories(),
        fetchFavoriteIds(),
    ]);
    await fetchItems();
    runWhenIdle(() => {
        checkClientDownloaderBootstrap();
        fetchSidebarStats();
        fetchCollections(renderCollectionsWrap);
        fetchTags(renderTagCloudWrap);
        fetchColors(fetchItems);
        fetchSmartCollections(() => renderSmartCollections(collDeps()));
    });

    // Open lightbox from ?item= param
    if (pendingItemId) {
        const idx = state.items.findIndex(it => it.id === pendingItemId);
        if (idx >= 0) openLightboxWrap(idx);
    }

    // Legacy: support #item= hash for backwards compatibility
    const hash = window.location.hash;
    const itemMatch = hash.match(/^#item=(\d+)$/);
    if (itemMatch) {
        const targetId = parseInt(itemMatch[1]);
        const idx = state.items.findIndex(it => it.id === targetId);
        if (idx >= 0) openLightboxWrap(idx);
    }
}

// Browser back/forward — re-hydrate state and re-fetch
window.addEventListener('popstate', () => {
    restoreStateFromUrl();
    fetchItems();
});

init();
