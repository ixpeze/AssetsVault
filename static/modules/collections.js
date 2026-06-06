// ── Collections Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { apiGet, apiPost, apiDelete } from './api.js';

export async function fetchCollections(renderCollections) {
    try {
        state.collections = await apiGet("/api/collections");
        renderCollections();
    } catch (err) {
        console.error("Failed to fetch collections:", err);
    }
}

export function renderCollections(deps) {
    const { showGallery, fetchItems, showToast } = deps;
    if (!state.collections.length) {
        dom.collectionsList.innerHTML = '<div class="px-3 py-1.5 text-[10px] text-text-muted italic">No collections yet</div>';
        return;
    }
    dom.collectionsList.innerHTML = state.collections.map(c => {
        const isActive = state.activeCollection === c.id;
        return `<a href="#" class="collection-link flex items-center gap-1 px-3 py-1.5 rounded text-xs ${isActive ? 'text-white bg-white/10 font-medium' : 'text-text-muted hover:text-white hover:bg-white/5'} transition-colors group" data-id="${c.id}">
            <span class="material-symbols-outlined text-[16px] ${isActive ? 'text-primary' : 'opacity-50'}">folder</span>
            <span class="truncate flex-1">${c.name}</span>
            <span class="text-[9px] opacity-50 bg-[#151515] px-1.5 rounded">${c.item_count}</span>
            <div class="hidden group-hover:flex items-center gap-0.5">
                <button class="rename-collection flex items-center justify-center w-4 h-4 rounded hover:bg-blue-500/20 text-text-muted hover:text-blue-400 transition-all" data-id="${c.id}" data-name="${c.name}" title="Rename">
                    <span class="material-symbols-outlined text-[12px]">edit</span>
                </button>
                <button class="export-collection flex items-center justify-center w-4 h-4 rounded hover:bg-green-500/20 text-text-muted hover:text-green-400 transition-all" data-id="${c.id}" data-name="${c.name}" title="Export JSON">
                    <span class="material-symbols-outlined text-[12px]">download</span>
                </button>
                <button class="delete-collection flex items-center justify-center w-4 h-4 rounded hover:bg-red-500/20 text-text-muted hover:text-red-400 transition-all" data-id="${c.id}" title="Delete">
                    <span class="material-symbols-outlined text-[12px]">close</span>
                </button>
            </div>
        </a>`;
    }).join("");

    dom.collectionsList.querySelectorAll(".collection-link").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            if (e.target.closest(".delete-collection") || e.target.closest(".rename-collection") || e.target.closest(".export-collection")) return;
            showGallery();
            const cid = parseInt(link.dataset.id);
            const col = state.collections.find(c => c.id === cid);
            if (state.activeCollection === cid) {
                state.activeCollection = null;
                dom.currentCategoryName.textContent = "All Assets";
            } else {
                state.activeCollection = cid;
                state.showFavorites = false;
                state.activeCategory = "";
                dom.currentCategoryName.textContent = col ? col.name : "Collection";
            }
            fetchItems();
            renderCollections(deps);
            if (window.innerWidth < 768) dom.sidebar.classList.remove("open");
        });
    });

    dom.collectionsList.querySelectorAll(".rename-collection").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation(); e.preventDefault();
            const cid = parseInt(btn.dataset.id);
            const oldName = btn.dataset.name;
            const newName = prompt("Rename collection:", oldName);
            if (!newName || newName === oldName) return;
            try {
                await fetch(`/api/collections/${cid}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: newName })
                });
                fetchCollections(() => renderCollections(deps));
                showToast("Collection renamed", "success");
            } catch (e) { showToast("Failed to rename collection", "error"); }
        });
    });

    dom.collectionsList.querySelectorAll(".export-collection").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation(); e.preventDefault();
            window.open(`/api/collections/${parseInt(btn.dataset.id)}/export`, "_blank");
            showToast("Exporting collection...", "success");
        });
    });

    dom.collectionsList.querySelectorAll(".delete-collection").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation(); e.preventDefault();
            const cid = parseInt(btn.dataset.id);
            if (!confirm("Delete this collection? Items won't be deleted.")) return;
            await apiDelete(`/api/collections/${cid}`);
            if (state.activeCollection === cid) state.activeCollection = null;
            fetchCollections(() => renderCollections(deps));
            showToast("Collection deleted");
        });
    });
}

export function openCollectionModal(addItemAfter = false, deps) {
    const { fetchCollections: fc, renderCollections: rc, showToast } = deps;
    dom.collectionModal.classList.remove("hidden");
    dom.collectionModal.classList.add("flex");
    dom.collectionNameInput.value = "";
    dom.collectionNameInput.focus();

    const handler = async () => {
        const name = dom.collectionNameInput.value.trim();
        if (!name) return;
        const result = await apiPost("/api/collections", { name });
        closeCollectionModal();
        await fc(() => rc(deps));
        showToast(`Created "${name}"`);
        if (addItemAfter && state.contextItemId && result.id) {
            await apiPost(`/api/collections/${result.id}/items`, { item_ids: [state.contextItemId] });
            fc(() => rc(deps));
        }
    };

    dom.modalCreate.onclick = handler;
    dom.collectionNameInput.onkeydown = (e) => { if (e.key === "Enter") handler(); };
}

export function closeCollectionModal() {
    dom.collectionModal.classList.add("hidden");
    dom.collectionModal.classList.remove("flex");
}

export function openCollectionPicker(showToast, renderCollectionPicker) {
    if (state.selectedIds.size === 0) { showToast("No items selected", "warning"); return; }
    dom.pickerCount.textContent = state.selectedIds.size;
    dom.pickerModal.classList.remove("hidden");
    dom.pickerModal.classList.add("flex");
    renderCollectionPicker();
}

export function closeCollectionPicker() {
    dom.pickerModal.classList.add("hidden");
    dom.pickerModal.classList.remove("flex");
}

export function renderCollectionPicker(deps) {
    const { bulkAddToCollection } = deps;
    if (!state.collections || state.collections.length === 0) {
        dom.pickerList.innerHTML = '<div class="text-center text-text-muted text-xs py-8">No collections yet. Create one from the sidebar.</div>';
        return;
    }
    dom.pickerList.innerHTML = state.collections.map(c => `
        <button class="picker-collection-btn w-full flex items-center gap-3 px-3 py-2.5 rounded-lg bg-white/5 hover:bg-white/10 border border-glass-border hover:border-primary/40 transition-all text-left group" data-id="${c.id}">
            <span class="material-symbols-outlined text-secondary text-[18px]">folder</span>
            <span class="flex-1 text-sm text-white">${c.name}</span>
            <span class="text-xs text-text-muted">${c.item_count || 0} items</span>
            <span class="material-symbols-outlined text-primary opacity-0 group-hover:opacity-100 text-[16px]">add</span>
        </button>
    `).join("");

    dom.pickerList.querySelectorAll(".picker-collection-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            const originalHtml = btn.innerHTML;
            btn.innerHTML = `<span class="material-symbols-outlined text-green-400 text-[18px]">check_circle</span>
                             <span class="flex-1 text-sm text-green-400">Added!</span>`;
            btn.classList.add("border-green-400/50", "bg-green-400/10");
            await bulkAddToCollection(parseInt(btn.dataset.id), deps);
            setTimeout(() => {
                btn.innerHTML = originalHtml;
                btn.classList.remove("border-green-400/50", "bg-green-400/10");
            }, 1000);
        });
    });
}

export async function bulkAddToCollection(collectionId, deps) {
    const { showToast, fetchCollections: fc, renderCollections: rc } = deps;
    const itemIds = Array.from(state.selectedIds);

    // Optimistic update
    const col = state.collections.find(c => c.id === collectionId);
    if (col) col.item_count = (col.item_count || 0) + itemIds.length;

    try {
        const result = await apiPost(`/api/collections/${collectionId}/items`, { item_ids: itemIds });
        if (result.success) {
            showToast(`Added ${itemIds.length} items to collection`, "success");
            closeCollectionPicker();
            // clearSelection called by init
            if (fc && rc) fc(() => rc(deps));
        }
    } catch (error) {
        showToast("Failed to add items to collection", "error");
        console.error(error);
    }
}

export async function fetchSmartCollections(renderSmartCollections) {
    try {
        state.smartCollections = await apiGet("/api/smart-collections");
        renderSmartCollections();
    } catch (e) {
        console.error("Failed to fetch smart collections", e);
    }
}

export function renderSmartCollections(deps) {
    const { applySmartCollectionFilters, showToast } = deps;
    const container = document.getElementById("smart-collections-list");
    if (!container) return;
    if (!state.smartCollections || !state.smartCollections.length) {
        container.innerHTML = '<div class="px-3 py-1.5 text-[10px] text-text-muted italic">No saved searches</div>';
        return;
    }
    container.innerHTML = state.smartCollections.map(sc =>
        `<a href="#" class="smart-collection-link flex items-center gap-1 px-3 py-1.5 rounded text-xs text-text-muted hover:text-white hover:bg-white/5 transition-colors group" data-id="${sc.id}" data-filters='${sc.filters}'>
            <span class="material-symbols-outlined text-[16px] text-emerald-400/50">saved_search</span>
            <span class="truncate flex-1">${sc.name}</span>
            <button class="delete-smart-collection hidden group-hover:flex items-center justify-center w-4 h-4 rounded hover:bg-red-500/20 text-text-muted hover:text-red-400 transition-all" data-id="${sc.id}">
                <span class="material-symbols-outlined text-[12px]">close</span>
            </button>
        </a>`
    ).join("");

    container.querySelectorAll(".smart-collection-link").forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            if (e.target.closest(".delete-smart-collection")) return;
            const filters = JSON.parse(link.dataset.filters || '{}');
            applySmartCollectionFilters(filters);
        });
    });

    container.querySelectorAll(".delete-smart-collection").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation(); e.preventDefault();
            await apiDelete(`/api/smart-collections/${btn.dataset.id}`);
            fetchSmartCollections(() => renderSmartCollections(deps));
            showToast("Saved search deleted");
        });
    });
}

export async function saveCurrentSearch(showToast, fetchSmartCollections) {
    const name = prompt("Name for this saved search:");
    if (!name) return;
    const filters = {
        q: state.searchQuery || "",
        category: state.activeCategory || "",
        tier: state.activeTier || "",
        tag: state.activeTag || "",
        color: state.activeColor || "",
        hasGdrive: state.advancedFilters.hasGdrive || "",
        fav: state.showFavorites ? "1" : "",
    };
    const hasFilters = Object.values(filters).some(v => v);
    if (!hasFilters) { showToast("No active filters to save"); return; }
    await apiPost("/api/smart-collections", { name, filters });
    fetchSmartCollections();
    showToast(`Saved search "${name}"`);
}

export async function importCollection(showToast, fetchCollections, renderCollections) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            const result = await apiPost("/api/collections/import", data);
            if (result.success) {
                showToast(`Imported "${result.name}" with ${result.added} items`);
                fetchCollections(() => renderCollections());
            }
        } catch (err) {
            console.error("Import failed", err);
            showToast("Failed to import collection");
        }
    };
    input.click();
}
