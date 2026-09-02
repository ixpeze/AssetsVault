// ── Obsidian Frost — Gallery Controller ──
// Handles item data fetching, pagination, infinite scroll sentinel, and grid loading state.

import { state } from './state.js';
import { dom } from './dom.js';
import { clearGridDOM, setGridItems } from './grid.js?v=4';
import { updateFooter, renderSkeleton } from './filters.js';
import { buildItemParams, pushStateToUrl } from './search.js';
import { showToast } from './toast.js';

let fetchItemsAbortController = null;
let _fillGridPending = false;
let _scrollObserver = null;

export async function fetchItems() {
    if (state.loading) return;
    state.loading = true;
    state.currentPage = 1;
    state.allLoaded = false;
    if (dom.emptyState) dom.emptyState.classList.add("hidden");
    if (dom.scrollEnd) dom.scrollEnd.classList.add("hidden");
    
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
            if (dom.emptyState) dom.emptyState.style.display = "";
        } else {
            if (dom.emptyState) dom.emptyState.style.display = "none";
            setGridItems(state.items);
        }

        updateFooter(state);
        pushStateToUrl();
        window.dispatchEvent(new Event('itemsFetched'));
        setTimeout(checkAndFillGrid, 100);
    } catch (e) {
        if (e.name !== 'AbortError') {
            console.error("fetchItems failed", e);
            showToast("Failed to load items", "error");
        }
    } finally {
        state.loading = false;
        if (dom.scrollLoader) dom.scrollLoader.classList.add("hidden");
    }
}

export function checkAndFillGrid() {
    if (_fillGridPending || state.loading || state.loadingMore || state.allLoaded) return;
    if (!dom.scrollSentinel) return;

    const rect = dom.scrollSentinel.getBoundingClientRect();
    const isVisible = rect.top < window.innerHeight;

    if (isVisible) {
        _fillGridPending = true;
        fetchMore().finally(() => { _fillGridPending = false; });
    }
}

export async function fetchMore() {
    if (state.loadingMore || state.allLoaded || state.loading) return;
    state.loadingMore = true;
    if (dom.scrollLoader) dom.scrollLoader.classList.remove("hidden");
    try {
        state.currentPage++;
        const params = buildItemParams();
        const resp = await fetch(`/api/items?${params.toString()}`);
        const data = await resp.json();
        const newItems = data.items || data;

        if (!newItems.length) {
            state.allLoaded = true;
            if (dom.scrollEnd) dom.scrollEnd.classList.remove("hidden");
            return;
        }

        state.items.push(...newItems);
        state.allLoaded = state.items.length >= state.total;

        setGridItems(state.items);
        updateFooter(state);
        if (state.allLoaded) {
            if (dom.scrollEnd) dom.scrollEnd.classList.remove("hidden");
            if (dom.scrollLoader) dom.scrollLoader.classList.add("hidden");
        }
        setTimeout(checkAndFillGrid, 100);
    } catch (e) {
        console.error("fetchMore failed", e);
        state.currentPage--;
    } finally {
        state.loadingMore = false;
        if (dom.scrollLoader) dom.scrollLoader.classList.add("hidden");
    }
}

export function initGalleryController() {
    if (dom.scrollSentinel && !_scrollObserver) {
        _scrollObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !state.allLoaded && !state.loading && !state.loadingMore) {
                fetchMore();
            }
        }, { threshold: 0.1 });
        _scrollObserver.observe(dom.scrollSentinel);
    }
}
