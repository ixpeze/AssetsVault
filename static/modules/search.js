// ── Search Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { apiGet } from './api.js';

export function buildItemParams() {
    const params = new URLSearchParams({
        page: state.currentPage,
        per_page: state.perPage,
    });
    if (state.searchQuery) params.set("q", state.searchQuery);
    if (state.activeTaxonomy) params.set("taxonomy", state.activeTaxonomy);
    else if (state.activeCategory) params.set("category", state.activeCategory);
    if (state.activeTier) params.set("tier", state.activeTier);
    if (state.sortBy && state.sortBy !== "newest") params.set("sort", state.sortBy);
    if (state.showFavorites) params.set("fav", "1");
    if (state.activeCollection) params.set("collection", state.activeCollection);
    if (state.activeTag) params.set("tag", state.activeTag);
    if (state.activeColor) params.set("color", state.activeColor);
    if (state.showUntagged) params.set("untagged", "1");
    if (state.semanticSearch && state.searchQuery) {
        params.set("semantic_q", state.searchQuery);
    }
    if (state.advancedFilters.hasGdrive === "yes") params.set("has_gdrive", "1");
    if (state.advancedFilters.hasGdrive === "no") params.set("no_gdrive", "1");
    if (state.advancedFilters.hasImage === "yes") params.set("has_image", "1");
    if (state.advancedFilters.hasImage === "no") params.set("no_image", "1");
    if (state.advancedFilters.tier) params.set("tier", state.advancedFilters.tier);

    const rawQ = state.searchQuery || '';
    const excludeTokens = rawQ.match(/-(\S+)/g);
    if (excludeTokens && excludeTokens.length > 0) {
        params.set('exclude_q', excludeTokens.map(t => t.slice(1)).join(' '));
        const cleanQ = rawQ.replace(/-\S+/g, '').trim();
        if (cleanQ) params.set('q', cleanQ); else params.delete('q');
    }

    if (state.activeTag && state.tagMode === 'OR') {
        params.set('tag_mode', 'or');
    }

    return params;
}

export function pushStateToUrl(openItemId = null) {
    const params = new URLSearchParams();
    if (state.searchQuery) params.set('q', state.searchQuery);
    if (state.activeTag) params.set('tag', state.activeTag);
    if (state.activeTaxonomy) params.set('taxonomy', state.activeTaxonomy);
    if (state.activeCategory) params.set('category', state.activeCategory);
    if (state.activeColor) params.set('color', state.activeColor);
    if (state.activeTier) params.set('tier', state.activeTier);
    if (state.showFavorites) params.set('fav', '1');
    if (state.showUntagged) params.set('untagged', '1');
    if (state.activeCollection) params.set('collection', state.activeCollection);
    if (state.sortBy && state.sortBy !== 'newest') params.set('sort', state.sortBy);
    if (state.currentPage > 1) params.set('page', state.currentPage);
    if (openItemId) params.set('item', openItemId);
    const qs = params.toString();
    history.replaceState(null, '', qs ? '?' + qs : window.location.pathname);
}

export function restoreStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('q')) { state.searchQuery = params.get('q'); dom.searchInput.value = state.searchQuery; }
    if (params.get('tag')) state.activeTag = params.get('tag');
    if (params.get('taxonomy')) state.activeTaxonomy = params.get('taxonomy');
    if (params.get('category')) state.activeCategory = params.get('category');
    if (params.get('color')) state.activeColor = params.get('color');
    if (params.get('tier')) state.activeTier = params.get('tier');
    if (params.get('fav') === '1') state.showFavorites = true;
    if (params.get('untagged') === '1') state.showUntagged = true;
    if (params.get('collection')) state.activeCollection = parseInt(params.get('collection'));
    if (params.get('sort')) state.sortBy = params.get('sort');
    if (params.get('page')) state.currentPage = parseInt(params.get('page')) || 1;
    // 'item' param is handled after fetchItems() completes in init()
    return params.get('item') ? parseInt(params.get('item')) : null;
}

export async function fetchStats() {
    try {
        const stats = await apiGet("/api/stats");
        state.stats = stats;
        if (dom.statTotalItems) dom.statTotalItems.textContent = stats.total_items || 0;
    } catch (err) {
        console.error("Failed to fetch stats:", err);
    }
}

export async function showAutocompleteSuggestions(query, setActiveCategory) {
    try {
        const suggestions = await apiGet(`/api/search/suggestions?q=${encodeURIComponent(query)}&limit=8`);
        const dropdown = document.getElementById("search-suggestions");

        if (!suggestions || suggestions.length === 0) {
            hideAutocompleteSuggestions();
            return;
        }

        dropdown.innerHTML = suggestions.map((s) => {
            const icon = s.type === 'tag' ? 'label' : 'folder';
            const color = s.type === 'tag' ? 'text-primary' : 'text-secondary';
            return `
                <button class="suggestion-item w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/5 transition-colors text-left"
                        data-type="${s.type}" data-value="${s.value}">
                    <span class="material-symbols-outlined ${color} text-[18px]">${icon}</span>
                    <span class="flex-1 text-sm text-white">${s.label}</span>
                    ${s.count ? `<span class="text-xs text-text-muted">${s.count.toLocaleString()}</span>` : ''}
                </button>
            `;
        }).join("");

        dropdown.classList.remove("hidden");

        dropdown.querySelectorAll(".suggestion-item").forEach(btn => {
            btn.addEventListener("click", () => {
                const type = btn.dataset.type;
                const value = btn.dataset.value;
                if (type === 'tag') {
                    state.activeTag = value;
                    dom.currentCategoryName.textContent = `Tag: ${value}`;
                } else {
                    setActiveCategory(value, value);
                }
                dom.searchInput.value = '';
                state.searchQuery = '';
                hideAutocompleteSuggestions();
                // fetchItems called externally via suggestion click handler in init
            });
        });
    } catch (e) {
        console.error("Failed to load suggestions", e);
    }
}

export function hideAutocompleteSuggestions() {
    document.getElementById("search-suggestions").classList.add("hidden");
}
