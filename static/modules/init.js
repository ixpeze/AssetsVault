// ── Obsidian Frost — Main Entry Point (ES Module) ──
// Modular Boot Coordinator & Event Dispatcher

import { state, tagManagerState } from './state.js';
import { dom } from './dom.js';
import { apiGet } from './api.js';
import { showToast } from './toast.js';
import { toggleSelection, clearSelection, updateSelectionUI } from './selection.js';
import { toggleFavorite, fetchFavoriteIds, refreshVisibleFavStars } from './favorites.js';
import { renderTaxonomyTree, attachTaxonomyListeners } from './taxonomy.js';
import { applyFilters, applyGridScale, setTierFilter } from './filters.js';
import { cleanTitle, buildCategoryTree, initCardDelegation } from './cards.js?v=4';
import { initVirtualGrid } from './grid.js?v=4';
import { checkClientDownloaderBootstrap, openDownloadsFolder, startActiveDownloadsMonitor } from './downloader.js?v=4';
import {
    buildItemParams, pushStateToUrl, restoreStateFromUrl, fetchStats,
    showAutocompleteSuggestions, hideAutocompleteSuggestions
} from './search.js';
import {
    openLightbox, closeLightbox, navigateLightbox,
    loadLightboxSimilar, renderLightboxCollectionDropdown
} from './lightbox.js';
import {
    fetchCollections, renderCollections, openCollectionModal,
    openCollectionPicker, renderCollectionPicker,
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
import { handleGalleryKey, clearFocus, updateColumnCount, toggleHelpOverlay } from './keyboard.js';
import { initDashboardTabs } from './dashboard-tabs.js';
import { fetchItems, fetchMore, initGalleryController } from './gallery-controller.js';
import { initThemeController, toggleFocusMode } from './theme-controller.js';
import { showContextMenu, initContextMenu } from './context-menu.js';

// ── Dependency bundles ──
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
    if (dom.currentCategoryName) dom.currentCategoryName.textContent = name || slug;
    fetchItems();
    renderTaxonomyTree();
    if (window.innerWidth < 768 && dom.sidebar) dom.sidebar.classList.remove("open");
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
    showGallery, fetchItems, showToast,
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

// ── Taxonomy & Categories ──
async function fetchCategories() {
    try {
        const cats = await apiGet("/api/categories");
        state.categories = Array.isArray(cats) ? cats : (cats.categories || []);
        state.categoryTree = buildCategoryTree(state.categories);
        state.taxonomyTree = await apiGet("/api/taxonomy").catch(() => state.categoryTree);
        renderTaxonomyTree();
        attachTaxonomyListeners(setActiveTaxonomy);
        updateCategoryCountBadges();
    } catch (e) {
        console.error("Failed to fetch categories", e);
    }
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

// ── Filters & Search ──
function showGalleryAndReset() {
    showGallery();
    state.showFavorites = false;
    state.activeCollection = null;
    if (dom.allAssetsLink) dom.allAssetsLink.classList.add("bg-frost-hover", "text-white");
    if (dom.favoritesLink) dom.favoritesLink.classList.remove("bg-frost-hover", "text-white");
}

function clearAllFilters() {
    state.searchQuery = ""; state.activeTag = ""; state.activeTaxonomy = ""; state.activeCategory = "";
    state.activeTier = ""; state.showFavorites = false;
    state.showUntagged = false; state.activeCollection = null;
    if (dom.searchInput) { dom.searchInput.value = ""; dom.searchClear?.classList.add("hidden"); }
    if (dom.activeTagFilter) dom.activeTagFilter.classList.add("hidden");
    if (dom.currentCategoryName) dom.currentCategoryName.textContent = "All Assets";
    if (dom.allAssetsLink) dom.allAssetsLink.classList.add("bg-frost-hover", "text-white");
    if (dom.favoritesLink) dom.favoritesLink.classList.remove("bg-frost-hover", "text-white");
    Object.keys(state.advancedFilters).forEach(k => state.advancedFilters[k] = "");
    ["filter-gdrive", "filter-image", "filter-tier", "filter-size", "filter-render", "filter-max-version"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = "";
    });
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
        state.activeTier || state.showFavorites || state.activeCollection ||
        Object.values(state.advancedFilters).some(v => v);
    pill.classList.toggle('hidden', !hasAny);
}

function applySmartCollectionFilters(filters) {
    showGallery();
    state.searchQuery = filters.q || "";
    state.activeCategory = filters.category || "";
    state.activeTier = filters.tier || "";
    state.activeTag = filters.tag || "";
    state.showFavorites = filters.fav === "1";
    state.advancedFilters.hasGdrive = filters.hasGdrive || "";
    if (dom.searchInput) dom.searchInput.value = state.searchQuery;
    fetchItems();
}

async function fetchSidebarStats() {
    try {
        const data = await apiGet('/api/counts');
        const uc = document.getElementById('stat-untagged-count');
        const mc = document.getElementById('stat-missing-count');
        if (uc) uc.textContent = data.untagged ?? '?';
        if (mc) mc.textContent = data.missing ?? '?';
    } catch (e) { /* optional */ }
}

function updateTagModeToggle() {
    const btn = document.getElementById('tag-mode-toggle');
    const lbl = document.getElementById('tag-mode-label');
    if (!btn || !lbl) return;
    lbl.textContent = state.tagMode;
    btn.classList.toggle('text-primary', state.tagMode === 'OR');
    btn.classList.toggle('text-text-muted', state.tagMode === 'AND');
    const hasTag = !!state.activeTag;
    btn.classList.toggle('hidden', !hasTag);
    btn.classList.toggle('flex', hasTag);
}

// ── Event Setup ──
function setupEventListeners() {
    // Navigation links
    dom.allAssetsLink?.addEventListener("click", (e) => {
        e.preventDefault();
        showGalleryAndReset();
        state.activeCategory = "";
        state.activeTaxonomy = "";
        dom.currentCategoryName.textContent = "All Assets";
        fetchItems();
        renderTaxonomyTree();
    });

    dom.favoritesLink?.addEventListener("click", (e) => {
        e.preventDefault();
        showGallery();
        state.showFavorites = !state.showFavorites;
        dom.favoritesLink.classList.toggle("bg-frost-hover", state.showFavorites);
        dom.favoritesLink.classList.toggle("text-white", state.showFavorites);
        dom.allAssetsLink.classList.toggle("bg-frost-hover", !state.showFavorites);
        dom.currentCategoryName.textContent = state.showFavorites ? "★ Favorites" : "All Assets";
        fetchItems();
    });

    dom.dashboardLink?.addEventListener("click", (e) => {
        e.preventDefault();
        const deps = { updateDashboard, fetchAnalytics, loadDbHealth, loadCoverageHeatmap };
        showDashboard(deps);
        initDashboardTabs(deps);
    });

    document.getElementById('open-downloads-folder')?.addEventListener('click', openDownloadsFolder);

    // Open item directly by ID (e.g. from autocomplete instant results)
    async function openItemById(targetId) {
        let idx = state.items.findIndex(it => it.id === targetId);
        if (idx >= 0) {
            openLightboxWrap(idx);
        } else {
            try {
                const item = await apiGet(`/api/items/${targetId}`);
                if (item && item.id) {
                    state.items.unshift(item);
                    openLightboxWrap(0);
                }
            } catch (e) {
                console.error("Failed to fetch item for preview", e);
            }
        }
    }

    // Search bar
    let searchTimer, autocompleteTimer;
    if (dom.searchInput) {
        dom.searchInput.addEventListener("input", (e) => {
            const val = e.target.value;
            state.searchQuery = val;
            dom.searchClear?.classList.toggle("hidden", !val);
            clearTimeout(searchTimer);
            clearTimeout(autocompleteTimer);
            if (val.length > 1) {
                autocompleteTimer = setTimeout(() => showAutocompleteSuggestions(val, {
                    setActiveCategory: setActiveTaxonomy,
                    fetchItems,
                    openLightboxById: openItemById
                }), 200);
            } else {
                hideAutocompleteSuggestions();
            }
            searchTimer = setTimeout(fetchItems, 250);
        });
        dom.searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { clearTimeout(searchTimer); hideAutocompleteSuggestions(); fetchItems(); }
            if (e.key === "Escape") { dom.searchInput.value = ""; state.searchQuery = ""; dom.searchClear?.classList.add("hidden"); hideAutocompleteSuggestions(); fetchItems(); }
        });
    }
    dom.searchClear?.addEventListener("click", () => {
        if (dom.searchInput) dom.searchInput.value = "";
        state.searchQuery = "";
        dom.searchClear.classList.add("hidden");
        hideAutocompleteSuggestions();
        fetchItems();
    });

    // Filters
    document.getElementById("filters-toggle")?.addEventListener("click", () => {
        document.getElementById("filters-panel")?.classList.toggle("hidden");
    });
    ["filter-gdrive", "filter-image", "filter-tier", "filter-size", "filter-render", "filter-max-version"].forEach(id => {
        document.getElementById(id)?.addEventListener("change", () => applyFilters(fetchItems));
    });
    document.getElementById("filters-clear")?.addEventListener("click", () => {
        Object.keys(state.advancedFilters).forEach(k => state.advancedFilters[k] = "");
        ["filter-gdrive", "filter-image", "filter-tier", "filter-size", "filter-render", "filter-max-version"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
        const badge = document.getElementById("active-filters-badge");
        if (badge) badge.classList.add("hidden");
        document.getElementById("filters-clear")?.classList.add("hidden");
        fetchItems();
    });

    // Sort & Grid Scale
    dom.sortSelect?.addEventListener("change", (e) => { state.sortBy = e.target.value; fetchItems(); });
    const savedScale = localStorage.getItem("gridScale") || "1";
    applyGridScale(savedScale);
    dom.gridScale?.addEventListener("input", (e) => applyGridScale(e.target.value));
    document.querySelectorAll(".grid-preset").forEach(btn => {
        btn.addEventListener("click", () => {
            if (dom.gridScale) dom.gridScale.value = btn.dataset.scale;
            applyGridScale(btn.dataset.scale);
            localStorage.setItem("gridScale", btn.dataset.scale);
        });
    });

    // Tier Pills
    const rebuildTree = () => { renderTaxonomyTree(); attachTaxonomyListeners(setActiveTaxonomy); };
    dom.pillAll?.addEventListener("click", () => setTierFilter("", rebuildTree, fetchItems));
    dom.pillFree?.addEventListener("click", () => setTierFilter("Free", rebuildTree, fetchItems));
    dom.pillPaid?.addEventListener("click", () => setTierFilter("Paid", rebuildTree, fetchItems));

    // Global clear
    document.getElementById('global-clear-filters')?.addEventListener('click', clearAllFilters);
    document.getElementById('focus-cat')?.addEventListener('click', clearAllFilters);
    window.addEventListener('itemsFetched', updateGlobalClearPill);

    // Lightbox triggers
    dom.lbClose?.addEventListener("click", closeLightboxWrap);
    dom.lbBackdrop?.addEventListener("click", closeLightboxWrap);
    dom.lbPrev?.addEventListener("click", () => navigateLightbox(-1, lbDeps()));
    dom.lbNext?.addEventListener("click", () => navigateLightbox(1, lbDeps()));

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
            navigator.clipboard.writeText(`${location.origin}${location.pathname}#item=${item.id}`)
                .then(() => showToast('Link copied!', 'success'));
        };
    }

    const btnSimilar = document.getElementById("lb-find-similar");
    if (btnSimilar) {
        btnSimilar.onclick = () => {
            const item = state.items[state.lightboxIndex];
            if (item) loadLightboxSimilar(item.id, lbDeps());
        };
    }

    // Scroll to top
    const scrollTopBtn = document.getElementById('scroll-to-top');
    if (scrollTopBtn && dom.scrollContainer) {
        dom.scrollContainer.addEventListener('scroll', () => {
            scrollTopBtn.classList.toggle('hidden', dom.scrollContainer.scrollTop < 500);
        });
        scrollTopBtn.addEventListener('click', () => dom.scrollContainer.scrollTo({ top: 0, behavior: 'smooth' }));
    }

    // Quick views
    const qvBtn = document.getElementById('quick-views-toggle');
    const qvPanel = document.getElementById('quick-views-panel');
    const qvChevron = document.getElementById('quick-views-chevron');
    if (qvBtn && qvPanel) {
        const open = localStorage.getItem('quickViewsOpen') === '1';
        if (open) { qvPanel.classList.remove('hidden'); if (qvChevron) qvChevron.style.transform = 'rotate(90deg)'; }
        qvBtn.addEventListener('click', () => {
            const isOpen = !qvPanel.classList.contains('hidden');
            qvPanel.classList.toggle('hidden', isOpen);
            if (qvChevron) qvChevron.style.transform = isOpen ? '' : 'rotate(90deg)';
            localStorage.setItem('quickViewsOpen', isOpen ? '0' : '1');
        });
    }

    // Tag manager modal & density
    dom.tagManagerBtn?.addEventListener("click", () => openTagManager(showToast, tagcloudDeps()));
    dom.tagManagerBackdrop?.addEventListener("click", closeTagManager);
    dom.tagManagerClose?.addEventListener("click", closeTagManager);
    dom.tagMergeBtn?.addEventListener("click", () => mergeTags(showToast));
    dom.tagDeleteBtn?.addEventListener("click", () => deleteTags(showToast, () => fetchTags(renderTagCloudWrap)));
    dom.clearTagFilter?.addEventListener("click", () => _clearTagFilter(tagcloudDeps()));

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

    // Keyboard bindings
    document.addEventListener("keydown", (e) => {
        if (e.key === '?' && !e.ctrlKey && !e.metaKey) { toggleHelpOverlay(); return; }

        const activeTag = document.activeElement.tagName;
        const isEditable = activeTag === "INPUT" || activeTag === "TEXTAREA" || activeTag === "SELECT" || document.activeElement.isContentEditable;

        if (state.lightboxIndex >= 0) {
            if (isEditable) return;
            if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); navigateLightbox(-1, lbDeps()); }
            if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); navigateLightbox(1, lbDeps()); }
            if (e.key === "Escape") closeLightboxWrap();
            if (e.key === "f" || e.key === "F") toggleFavorite(state.items[state.lightboxIndex]?.id).then(refreshVisibleFavStars);
            return;
        }

        if (e.key === "/" || (e.key === "k" && (e.ctrlKey || e.metaKey))) { e.preventDefault(); dom.searchInput?.focus(); dom.searchInput?.select(); return; }
        if (e.key === "F2") { toggleFocusMode(); return; }
        if (e.key === "Escape") { clearSelection(); updateSelectionUI(); return; }
        if (e.key === "a" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); state.items.forEach(i => state.selectedIds.add(i.id)); updateSelectionUI(); return; }

        if (!isEditable) {
            handleGalleryKey(e, {
                openLightbox: openLightboxWrap,
                toggleFavorite: (id) => toggleFavorite(id).then(refreshVisibleFavStars),
                toggleSelection,
                updateSelectionUI,
            });
        }
    });

    window.addEventListener('itemsFetched', () => { clearFocus(); setTimeout(updateColumnCount, 100); });
    window.addEventListener('resize', updateColumnCount);
    window.addEventListener('popstate', () => { restoreStateFromUrl(); fetchItems(); });
}

// ── Window Action Handlers ──
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

// ── Main Init Bootstrap ──
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
    initGalleryController();
    initThemeController(fetchItems);
    initContextMenu({
        toggleFavorite,
        refreshVisibleFavStars,
        openCollectionPicker,
        openCollectionModal,
        renderCollectionPicker,
        collDeps,
        showToast
    });
    startActiveDownloadsMonitor();
    setupEventListeners();

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
        fetchSmartCollections(() => renderSmartCollections(collDeps()));
    });

    if (pendingItemId) {
        const idx = state.items.findIndex(it => it.id === pendingItemId);
        if (idx >= 0) openLightboxWrap(idx);
    }

    const hash = window.location.hash;
    const itemMatch = hash.match(/^#item=(\d+)$/);
    if (itemMatch) {
        const targetId = parseInt(itemMatch[1]);
        const idx = state.items.findIndex(it => it.id === targetId);
        if (idx >= 0) openLightboxWrap(idx);
    }
}

init();
