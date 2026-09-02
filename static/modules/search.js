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
    if (state.showUntagged) params.set("untagged", "1");
    if (state.advancedFilters.hasGdrive === "yes") params.set("has_gdrive", "1");
    if (state.advancedFilters.hasGdrive === "no") params.set("no_gdrive", "1");
    if (state.advancedFilters.hasImage === "yes") params.set("has_image", "1");
    if (state.advancedFilters.hasImage === "no") params.set("no_image", "1");
    if (state.advancedFilters.hasSize === "yes") params.set("has_size", "1");
    if (state.advancedFilters.hasSize === "no") params.set("no_size", "1");
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

export async function showAutocompleteSuggestions(query, options = {}) {
    try {
        const { setActiveCategory, fetchItems, openLightboxById } = typeof options === 'function' 
            ? { setActiveCategory: options } 
            : options;

        const data = await apiGet(`/api/search/suggestions?q=${encodeURIComponent(query)}&limit=8`);
        const dropdown = document.getElementById("search-suggestions");
        if (!dropdown) return;

        // Support both new grouped schema and legacy array schema
        const isGrouped = data && !Array.isArray(data) && (data.categories || data.phrases || data.items);
        const categories = isGrouped ? (data.categories || []) : (Array.isArray(data) ? data.filter(d => d.type === 'category') : []);
        const phrases = isGrouped ? (data.phrases || []) : (Array.isArray(data) ? data.filter(d => d.type === 'tag') : []);
        const items = isGrouped ? (data.items || []) : [];

        const hasResults = categories.length > 0 || phrases.length > 0 || items.length > 0;
        if (!hasResults) {
            hideAutocompleteSuggestions();
            return;
        }

        let html = '<div class="py-2 divide-y divide-white/5">';

        // 1. Categories Section
        if (categories.length > 0) {
            html += `
                <div class="px-3 py-1.5">
                    <div class="text-[10px] font-semibold tracking-wider text-text-muted uppercase px-2 mb-1">Categories</div>
                    <div class="space-y-0.5">
                        ${categories.map(c => `
                            <button class="suggestion-item group w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md hover:bg-white/5 transition-colors text-left"
                                    data-type="category" data-slug="${c.slug}" data-name="${c.name}">
                                <span class="material-symbols-outlined text-primary text-[18px] shrink-0 group-hover:scale-110 transition-transform">folder</span>
                                <span class="flex-1 text-xs font-medium text-slate-200 group-hover:text-white truncate">${c.name}</span>
                                <span class="text-[11px] text-text-muted bg-white/5 px-1.5 py-0.5 rounded font-mono">${(c.count || 0).toLocaleString()}</span>
                            </button>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        // 2. Search Phrases Section
        if (phrases.length > 0) {
            html += `
                <div class="px-3 py-1.5">
                    <div class="text-[10px] font-semibold tracking-wider text-text-muted uppercase px-2 mb-1">Suggested Searches</div>
                    <div class="space-y-0.5">
                        ${phrases.map(p => `
                            <button class="suggestion-item group w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md hover:bg-white/5 transition-colors text-left"
                                    data-type="phrase" data-text="${p.text || p.value}">
                                <span class="material-symbols-outlined text-accent text-[18px] shrink-0 group-hover:scale-110 transition-transform">search</span>
                                <span class="flex-1 text-xs text-slate-300 group-hover:text-white truncate">${p.text || p.label || p.value}</span>
                                ${p.count ? `<span class="text-[11px] text-text-muted font-mono">${p.count.toLocaleString()}</span>` : ''}
                            </button>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        // 3. Item Previews Section
        if (items.length > 0) {
            html += `
                <div class="px-3 py-1.5">
                    <div class="text-[10px] font-semibold tracking-wider text-text-muted uppercase px-2 mb-1">Instant Results</div>
                    <div class="space-y-1">
                        ${items.map(it => `
                            <button class="suggestion-item group w-full flex items-center gap-3 px-2.5 py-1.5 rounded-md hover:bg-white/5 transition-colors text-left"
                                    data-type="item" data-id="${it.id}">
                                <div class="w-8 h-8 rounded bg-black/40 border border-white/10 overflow-hidden shrink-0 flex items-center justify-center">
                                    ${it.image_url ? `<img src="${it.image_url}" class="w-full h-full object-cover" onerror="this.style.display='none'" />` : '<span class="material-symbols-outlined text-text-muted text-[14px]">view_in_ar</span>'}
                                </div>
                                <div class="flex-1 min-w-0">
                                    <div class="text-xs font-medium text-slate-200 group-hover:text-white truncate">${it.title}</div>
                                    <div class="text-[10px] text-text-muted truncate">${it.category_slug || ''}</div>
                                </div>
                                <span class="material-symbols-outlined text-text-muted text-[16px] opacity-0 group-hover:opacity-100 transition-opacity">arrow_forward</span>
                            </button>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        html += '</div>';
        dropdown.innerHTML = html;
        dropdown.classList.remove("hidden");

        // Attach click listeners to all items
        dropdown.querySelectorAll(".suggestion-item").forEach(btn => {
            btn.addEventListener("click", () => {
                const type = btn.dataset.type;
                if (type === 'category') {
                    const slug = btn.dataset.slug;
                    const name = btn.dataset.name;
                    if (dom.searchInput) dom.searchInput.value = '';
                    state.searchQuery = '';
                    if (setActiveCategory) setActiveCategory(slug, name);
                } else if (type === 'phrase') {
                    const text = btn.dataset.text;
                    if (dom.searchInput) dom.searchInput.value = text;
                    state.searchQuery = text;
                    state.activeCategory = '';
                    state.activeTaxonomy = '';
                    if (fetchItems) fetchItems();
                } else if (type === 'item') {
                    const id = parseInt(btn.dataset.id, 10);
                    if (openLightboxById) {
                        openLightboxById(id);
                    } else {
                        // Fallback: search for this exact item
                        if (dom.searchInput) dom.searchInput.value = btn.querySelector('.text-xs')?.textContent || '';
                        state.searchQuery = dom.searchInput.value;
                        if (fetchItems) fetchItems();
                    }
                }
                hideAutocompleteSuggestions();
            });
        });
    } catch (e) {
        console.error("Failed to load suggestions", e);
    }
}

export function hideAutocompleteSuggestions() {
    const dropdown = document.getElementById("search-suggestions");
    if (dropdown) dropdown.classList.add("hidden");
}

