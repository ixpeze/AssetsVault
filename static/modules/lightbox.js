// ── Lightbox Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { apiGet, apiPost, apiDelete } from './api.js';
import { escapeAttr, escapeHtml, formatBytes } from './cards.js';

let lbZoomed = false;

export function openLightbox(index, deps) {
    const { cleanTitle, setActiveTaxonomy, fetchItems, showToast, closeLightbox: cl, fetchMore } = deps;
    if (index < 0 || index >= state.items.length) return;
    state.lightboxIndex = index;
    const item = state.items[index];

    lbZoomed = false;
    dom.lbImage.style.transform = '';
    // Smooth image load: fade out → swap src → fade in
    dom.lbImage.style.opacity = '0';
    dom.lbImage.style.transition = 'opacity 0.15s ease';
    dom.lbImage.onload = () => { dom.lbImage.style.opacity = '1'; };
    dom.lbImage.onerror = () => { dom.lbImage.style.opacity = '0.3'; };
    dom.lbImage.src = item.local_image_url || item.image_url || "";
    dom.lbImage.alt = cleanTitle(item.title);
    dom.lbTitle.textContent = cleanTitle(item.title);

    const catBtn = document.getElementById('lb-category-btn');
    if (catBtn) {
        const catLabel = item.category_slug ? item.category_slug.replace(/-/g, " ") : "Uncategorized";
        catBtn.textContent = catLabel;
        catBtn.onclick = () => { closeLightbox(deps); if (item.category_slug) setActiveTaxonomy(item.category_slug, catLabel); };
    }

    const isPaid = item.tier === "Paid";
    dom.lbTierDot.className = `w-2 h-2 rounded-full ${isPaid ? 'bg-[#F59E0B] shadow-[0_0_6px_rgba(245,158,11,0.6)]' : 'bg-[#4ADE80] shadow-[0_0_6px_rgba(74,222,128,0.5)]'}`;
    dom.lbDate.textContent = item.collected_at ? new Date(item.collected_at).toLocaleDateString() : "—";

    const idValEl = document.getElementById('lb-id-val');
    if (idValEl) idValEl.textContent = item.id || '—';
    else if (dom.lbId) dom.lbId.textContent = item.id || '—';

    if (dom.lbSize && dom.lbSizeContainer) {
        if (item.file_size) {
            dom.lbSize.textContent = formatBytes(item.file_size);
            dom.lbSizeContainer.classList.remove('hidden');
        } else {
            dom.lbSizeContainer.classList.add('hidden');
        }
    }

    setLinkBtn(dom.lbGdrive, item.gdrive_link);
    setLinkBtn(dom.lbMirror, item.mirror_link);
    setLinkBtn(dom.lbSource, item.post_url);
    dom.lbCounter.textContent = `${index + 1} / ${state.items.length}${state.allLoaded ? '' : '+'}`;

    const simGrid = document.getElementById('lb-similar-grid');
    if (simGrid) simGrid.innerHTML = '<div class="col-span-4 text-xs text-text-muted italic">Click Load to find similar items</div>';
    const viewAllLink = document.getElementById('lb-view-all-similar');
    if (viewAllLink) viewAllLink.classList.add('hidden');

    const tagsContainer = document.getElementById("lb-tags");
    if (tagsContainer) {
        tagsContainer.innerHTML = "";
        if (item.tags && item.tags.length > 0) {
            item.tags.forEach(tag => {
                const wrapper = document.createElement("div");
                wrapper.className = "group flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium border transition-colors " +
                    (tag.source === 'ai'
                        ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                        : "bg-white/5 border-white/10 text-text-muted");
                const tagBtn = document.createElement("button");
                tagBtn.textContent = tag.source === 'ai' ? `✨ ${tag.name}` : tag.name;
                tagBtn.className = "hover:text-white transition-colors";
                tagBtn.addEventListener("click", () => {
                    closeLightbox(deps);
                    state.activeTag = tag.name;
                    state.activeCategory = "";
                    state.showFavorites = false;
                    state.activeCollection = null;
                    state.searchQuery = "";
                    dom.searchInput.value = "";
                    dom.currentCategoryName.textContent = `Tag: ${tag.name}`;
                    const tagFilter = document.getElementById("active-tag-filter");
                    const tagText = document.getElementById("active-tag-name");
                    if (tagFilter && tagText) { tagFilter.classList.remove("hidden"); tagText.textContent = tag.name; }
                    fetchItems();
                });
                const removeBtn = document.createElement("button");
                removeBtn.innerHTML = "×";
                removeBtn.className = "opacity-0 group-hover:opacity-100 ml-1 hover:text-red-400 transition-all font-bold";
                removeBtn.onclick = (e) => { e.stopPropagation(); removeTagFromItem(item.id, tag.id, tag.name, deps); };
                wrapper.appendChild(tagBtn);
                wrapper.appendChild(removeBtn);
                tagsContainer.appendChild(wrapper);
            });
        } else {
            tagsContainer.innerHTML = '<span class="text-[10px] text-text-muted italic">No tags — add one below</span>';
        }
    }

    dom.lightbox.classList.remove("hidden");
    dom.lightbox.classList.add("active");
    dom.lightbox.setAttribute("role", "dialog");
    dom.lightbox.setAttribute("aria-modal", "true");
    dom.lightbox.setAttribute("aria-label", `Viewing ${cleanTitle(item.title)}`);
    document.body.style.overflow = "hidden";
    history.replaceState(null, '', `#item=${item.id}`);

    const paletteContainer = document.getElementById("color-swatches");
    if (paletteContainer) paletteContainer.innerHTML = '<div class="text-xs text-text-muted italic">Loading...</div>';
    loadLightboxColors(item.id, deps);
}

export function closeLightbox(deps) {
    dom.lightbox.classList.remove("active");
    state.lightboxIndex = -1;
    document.body.style.overflow = "";
    lbZoomed = false;
    dom.lbImage.style.transform = '';
    history.replaceState(null, '', window.location.pathname + window.location.search);
    const dropdown = document.getElementById('lb-collection-dropdown');
    if (dropdown) dropdown.classList.add('hidden');
}

export async function navigateLightbox(dir, deps) {
    const { fetchMore, showToast } = deps;
    const next = state.lightboxIndex + dir;
    if (next >= state.items.length && !state.allLoaded) {
        try { await fetchMore(); } catch (e) { /* ignore */ }
        if (next < state.items.length) openLightbox(next, deps);
        else showToast('Reached end of results', 'info');
        return;
    }
    if (next >= 0 && next < state.items.length) openLightbox(next, deps);
    else if (next < 0) showToast('At beginning', 'info');
    else showToast('Reached end of results', 'info');
}

export async function loadLightboxColors(itemId, deps) {
    const paletteContainer = document.getElementById("color-swatches");
    if (!paletteContainer) return;
    try {
        const colors = await apiGet(`/api/items/${itemId}/colors`);
        paletteContainer.innerHTML = "";
        if (colors.length === 0) {
            paletteContainer.innerHTML = '<div class="col-span-full text-xs text-text-muted italic">No colors extracted</div>';
            return;
        }
        colors.forEach(c => {
            const btn = document.createElement("button");
            btn.className = "w-6 h-6 rounded-full border border-white/10 hover:scale-110 transition-transform cursor-pointer relative tooltip-trigger";
            btn.style.backgroundColor = c.hex;
            btn.title = `${c.percentage ? Math.round(c.percentage * 100) : ''}%`;
            btn.onclick = () => searchWithColor(c.hex, deps);
            paletteContainer.appendChild(btn);
        });
    } catch (e) {
        console.error("Failed to load item colors", e);
        paletteContainer.innerHTML = '<div class="col-span-full text-xs text-red-500">Error</div>';
    }
}

export function searchWithColor(hex, deps) {
    if (deps) {
        closeLightbox(deps);
        state.activeColor = hex;
        if (deps.fetchItems) deps.fetchItems();
    } else {
        // fallback when called without deps (e.g. from gallery context)
        state.activeColor = hex;
    }
}

export function setLinkBtn(el, url) {
    if (el) {
        if (url) { el.href = url; el.classList.remove("opacity-30", "pointer-events-none"); }
        else { el.href = "#"; el.classList.add("opacity-30", "pointer-events-none"); }
    }
}

export async function addTagToItem(itemId, tagName, deps) {
    const { showToast } = deps;
    try {
        const result = await apiPost(`/api/items/${itemId}/tags`, { tag: tagName });
        if (result.success) {
            const item = state.items[state.lightboxIndex];
            if (!item.tags) item.tags = [];
            item.tags.push({ id: result.tag_id, name: result.tag_name, source: 'manual' });
            openLightbox(state.lightboxIndex, deps);
            showToast(`Tag "${tagName}" added`, "success");
        }
    } catch (e) { console.error("Failed to add tag", e); showToast("Failed to add tag", "error"); }
}

export async function removeTagFromItem(itemId, tagId, tagName, deps) {
    const { showToast } = deps;
    try {
        const result = await apiDelete(`/api/items/${itemId}/tags/${tagId}`);
        if (result.success) {
            const item = state.items[state.lightboxIndex];
            if (item.tags) item.tags = item.tags.filter(t => t.id !== tagId);
            openLightbox(state.lightboxIndex, deps);
            showToast(`Tag "${tagName}" removed`, "success");
        }
    } catch (e) { console.error("Failed to remove tag", e); showToast("Failed to remove tag", "error"); }
}

export async function loadLightboxSimilar(itemId, deps) {
    const { cleanTitle, showToast } = deps;
    const grid = document.getElementById('lb-similar-grid');
    const viewAll = document.getElementById('lb-view-all-similar');
    if (!grid) return;
    grid.innerHTML = '<div class="col-span-4 text-xs text-text-muted"><span class="animate-pulse">Finding similar...</span></div>';
    try {
        const items = await apiGet(`/api/similar/${itemId}`);
        if (!items || items.length === 0) {
            grid.innerHTML = '<div class="col-span-4 text-xs text-text-muted italic">No similar items found. Run AI tagging first.</div>';
            return;
        }
        grid.dataset.sourceId = itemId;
        grid.innerHTML = items.slice(0, 8).map(it => {
            const img = it.local_image_url || it.image_url || '';
            const title = cleanTitle(it.title || '');
            return `<button class="lb-sim-thumb aspect-square rounded overflow-hidden border border-glass-border hover:border-primary/60 transition-all cursor-pointer relative group"
                data-item-id="${it.id}" title="${escapeAttr(title)}">
                <img src="${escapeAttr(img)}" alt="${escapeAttr(title)}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200" loading="lazy" />
            </button>`;
        }).join('');
        grid.querySelectorAll('.lb-sim-thumb').forEach(btn => {
            btn.addEventListener('click', () => {
                const clickedId = parseInt(btn.dataset.itemId);
                let idx = state.items.findIndex(it => it.id === clickedId);
                if (idx >= 0) openLightbox(idx, deps);
                else {
                    apiGet(`/api/items/${clickedId}`).then(item => {
                        if (item && item.id) { state.items.push(item); openLightbox(state.items.length - 1, deps); }
                    }).catch(() => showToast('Could not load item', 'error'));
                }
            });
        });
        if (viewAll) { viewAll.classList.remove('hidden'); viewAll.textContent = `View all ${items.length} similar in gallery →`; }
    } catch (e) {
        console.error("Inline similar failed", e);
        grid.innerHTML = '<div class="col-span-4 text-xs text-red-500">Failed to load similar items</div>';
    }
}

export function renderLightboxCollectionDropdown(fetchCollections, showToast) {
    const dropdown = document.getElementById('lb-collection-dropdown');
    if (!dropdown) return;
    if (!state.collections || state.collections.length === 0) {
        dropdown.innerHTML = '<div class="px-3 py-4 text-xs text-text-muted text-center">No collections yet</div>';
        return;
    }
    dropdown.innerHTML = state.collections.map(c => `
        <button class="lb-col-pick w-full flex items-center gap-2 px-3 py-2 hover:bg-white/10 transition-colors text-left text-xs" data-id="${c.id}">
            <span class="material-symbols-outlined text-[14px] text-secondary">folder</span>
            <span class="flex-1 text-white truncate">${escapeHtml(c.name)}</span>
            <span class="text-text-muted">${c.item_count || 0}</span>
        </button>
    `).join('');
    dropdown.querySelectorAll('.lb-col-pick').forEach(btn => {
        btn.addEventListener('click', async () => {
            const collectionId = parseInt(btn.dataset.id);
            const item = state.items[state.lightboxIndex];
            if (!item) return;

            // Visual feedback
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<span class="material-symbols-outlined text-green-400 text-[14px]">check_circle</span>
                             <span class="flex-1 text-green-400 text-xs">Added!</span>`;
            btn.classList.add("bg-green-400/10");

            // Optimistic update
            const col = state.collections.find(c => c.id === collectionId);
            if (col) col.item_count = (col.item_count || 0) + 1;

            try {
                const result = await apiPost(`/api/collections/${collectionId}/items`, { item_ids: [item.id] });
                if (result.success) {
                    showToast(`Added to "${btn.querySelector('span:nth-child(2)').textContent}"`, 'success');
                    fetchCollections(); // Refetches and re-renders sidebar
                }
            } catch (e) { showToast('Failed to add to collection', 'error'); }

            setTimeout(() => {
                btn.innerHTML = originalHtml;
                btn.classList.remove("bg-green-400/10");
                dropdown.classList.add('hidden');
            }, 600);
        });
    });
}
