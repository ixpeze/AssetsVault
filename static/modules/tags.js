// ── Tags Module (Tag Cloud + Tag Manager) ──
import { state, tagManagerState } from './state.js';
import { dom } from './dom.js';
import { apiGet, apiPost, apiDelete } from './api.js';

export async function fetchTags(renderTagCloud) {
    try {
        state.tags = await apiGet("/api/tags?limit=100");
        renderTagCloud();
    } catch (err) {
        console.error("Failed to fetch tags:", err);
    }
}

export function renderTagCloud(deps) {
    const { showGallery, fetchItems, showToast, clearTagFilter } = deps;
    if (!state.tags.length) {
        dom.tagCloud.innerHTML = '<span class="text-[10px] text-text-muted italic">No tags yet</span>';
        return;
    }
    const visibleTags = state.tags.slice(0, state.tagDensity || 30);
    const maxCount = Math.max(...visibleTags.map(t => t.count));
    dom.tagCloud.innerHTML = visibleTags.map(t => {
        const size = Math.max(10, Math.min(16, 10 + (t.count / maxCount) * 6));
        const opacity = Math.max(0.4, Math.min(1, 0.4 + (t.count / maxCount) * 0.6));
        const isActive = state.activeTag === t.name;
        return `<button class="tag-btn px-2 py-0.5 rounded-full border transition-all ${isActive ? 'bg-primary/20 border-primary/40 text-primary' : 'border-glass-border text-text-muted hover:text-white hover:border-white/30'}" style="font-size:${size}px; opacity:${isActive ? 1 : opacity}" data-tag="${t.name}" title="${t.count} items">${t.name}</button>`;
    }).join("");

    dom.tagCloud.querySelectorAll(".tag-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            showGallery();
            const tag = btn.dataset.tag;
            if (state.activeTag === tag) {
                clearTagFilter(deps);
            } else {
                state.activeTag = tag;
                state.activeCollection = null;
                state.showFavorites = false;
                dom.activeTagName.textContent = tag;
                dom.activeTagFilter.classList.remove("hidden");
                dom.activeTagFilter.classList.add("flex");
                dom.currentCategoryName.textContent = `Tag: ${tag}`;
                fetchItems();
                renderTagCloud(deps);
                if (window.innerWidth < 768) dom.sidebar.classList.remove("open");
            }
        });
    });
}

export function clearTagFilter(deps) {
    const { showGallery, fetchItems, renderTagCloud: rtc } = deps;
    showGallery();
    state.activeTag = "";
    dom.activeTagFilter.classList.add("hidden");
    dom.activeTagFilter.classList.remove("flex");
    dom.currentCategoryName.textContent = "All Assets";
    fetchItems();
    rtc(deps);
}

// Tag Manager
export async function openTagManager() {
    dom.tagManagerModal.classList.remove("hidden");
    dom.tagManagerModal.classList.add("flex");
    await loadAllTags();
    renderTagManager();
}

export function closeTagManager() {
    dom.tagManagerModal.classList.add("hidden");
    dom.tagManagerModal.classList.remove("flex");
    tagManagerState.selectedTagIds.clear();
}

export async function loadAllTags() {
    try {
        const tags = await apiGet("/api/tags?limit=1000");
        tagManagerState.allTags = tags;
        tagManagerState.filteredTags = tags;
        dom.tagTotalCount.textContent = `${tags.length} tags`;
    } catch (error) {
        console.error("Failed to load tags:", error);
    }
}

export function renderTagManager() {
    const tags = tagManagerState.filteredTags;
    if (tags.length === 0) {
        dom.tagList.innerHTML = '<div class="text-center text-text-muted text-xs py-8">No tags found</div>';
        return;
    }
    dom.tagList.innerHTML = tags.map(tag => {
        const isSelected = tagManagerState.selectedTagIds.has(tag.id);
        const sourceColor = tag.source === 'auto' ? 'text-purple-400' : 'text-primary';
        const sourceBadge = tag.source === 'auto' ? 'AUTO' : 'MANUAL';
        return `
            <div class="tag-manager-item flex items-center gap-3 px-3 py-2.5 rounded-lg ${isSelected ? 'bg-primary/20 border-primary/40' : 'bg-white/5 hover:bg-white/10'} border ${isSelected ? 'border-primary/40' : 'border-glass-border'} transition-all group">
                <input type="checkbox" class="tag-checkbox w-4 h-4 rounded border-glass-border bg-void checked:bg-primary checked:border-primary cursor-pointer"
                       data-tag-id="${tag.id}" ${isSelected ? 'checked' : ''}>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                        <span class="tag-name-display text-sm text-white font-medium truncate">${tag.name}</span>
                        <span class="text-[9px] font-mono ${sourceColor} px-1.5 py-0.5 rounded bg-black/20">${sourceBadge}</span>
                    </div>
                    <div class="text-xs text-text-muted">${tag.count} items</div>
                </div>
                <button class="tag-rename-btn opacity-0 group-hover:opacity-100 flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 text-text-muted hover:text-white transition-all"
                        data-tag-id="${tag.id}" data-tag-name="${tag.name}" title="Rename">
                    <span class="material-symbols-outlined text-[16px]">edit</span>
                </button>
            </div>
        `;
    }).join("");

    dom.tagList.querySelectorAll(".tag-checkbox").forEach(checkbox => {
        checkbox.addEventListener("change", (e) => {
            const tagId = parseInt(e.target.dataset.tagId);
            if (e.target.checked) tagManagerState.selectedTagIds.add(tagId);
            else tagManagerState.selectedTagIds.delete(tagId);
            updateTagManagerUI();
        });
    });

    dom.tagList.querySelectorAll(".tag-rename-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            await renameTag(parseInt(btn.dataset.tagId), btn.dataset.tagName);
        });
    });
}

export function updateTagManagerUI() {
    const count = tagManagerState.selectedTagIds.size;
    if (count > 0) {
        dom.tagSelectedCount.classList.remove("hidden");
        dom.tagSelectedCount.textContent = `${count} selected`;
        dom.tagDeselectAll.classList.remove("hidden");
        dom.tagMergeBtn.classList.toggle("hidden", count < 2);
        dom.tagDeleteBtn.classList.remove("hidden");
    } else {
        dom.tagSelectedCount.classList.add("hidden");
        dom.tagDeselectAll.classList.add("hidden");
        dom.tagMergeBtn.classList.add("hidden");
        dom.tagDeleteBtn.classList.add("hidden");
    }
    renderTagManager();
}

export async function renameTag(tagId, oldName, showToast, fetchTagsFn) {
    const btn = dom.tagList?.querySelector(`.tag-rename-btn[data-tag-id="${tagId}"]`);
    const nameSpan = btn?.closest('.tag-manager-item')?.querySelector('.tag-name-display');
    if (!nameSpan) return;

    const inp = document.createElement('input');
    inp.className = 'bg-transparent border-b border-primary text-white text-sm px-0 focus:outline-none w-36';
    inp.value = oldName;
    nameSpan.replaceWith(inp);
    inp.focus();
    inp.select();

    let finished = false;
    const finish = async (save) => {
        if (finished) return;
        finished = true;
        const newName = inp.value.trim().toLowerCase();
        if (save && newName && newName !== oldName) {
            try {
                const result = await fetch(`/api/tags/${tagId}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: newName })
                }).then(r => r.json());
                if (result.success) {
                    if (showToast) showToast(`Renamed to "${newName}"`, "success");
                    await loadAllTags();
                    renderTagManager();
                    if (fetchTagsFn) fetchTagsFn();
                    return;
                } else {
                    if (showToast) showToast(result.error || "Rename failed", "error");
                }
            } catch (e) { console.error(e); if (showToast) showToast("Rename failed", "error"); }
        }
        const restored = document.createElement('span');
        restored.className = 'tag-name-display text-sm text-white font-medium truncate';
        restored.textContent = oldName;
        inp.replaceWith(restored);
    };

    inp.addEventListener('blur', () => finish(true));
    inp.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); finish(true); }
        if (e.key === 'Escape') finish(false);
    });
}

export function mergeTags(showToast) {
    const selectedIds = Array.from(tagManagerState.selectedTagIds);
    if (selectedIds.length < 2) { showToast("Select at least 2 tags to merge", "warning"); return; }
    const dialog = document.getElementById("merge-dialog");
    const countEl = document.getElementById("merge-count");
    const targetInput = document.getElementById("merge-target-input");
    if (!dialog || !targetInput) return;
    countEl.textContent = selectedIds.length;
    const firstTag = tagManagerState.allTags.find(t => t.id === selectedIds[0]);
    if (firstTag) targetInput.value = firstTag.name;
    dialog.classList.remove("hidden");
    targetInput.focus();
    targetInput.select();
}

export async function _executeMerge(targetName, showToast, fetchTagsFn) {
    const selectedIds = Array.from(tagManagerState.selectedTagIds);
    if (!targetName || selectedIds.length < 2) return;
    const normalizedTarget = targetName.trim().toLowerCase();
    let targetTag = tagManagerState.allTags.find(t => t.name === normalizedTarget);
    let targetId;
    try {
        if (targetTag) {
            targetId = targetTag.id;
            const sourceIds = selectedIds.filter(id => id !== targetId);
            if (sourceIds.length === 0) { showToast("No other tags to merge", "warning"); return; }
            const result = await apiPost("/api/tags/merge", { source_ids: sourceIds, target_id: targetId });
            if (result.success) showToast(`Merged ${result.merged} tags into "${normalizedTarget}"`, "success");
        } else {
            targetId = selectedIds[0];
            const otherIds = selectedIds.slice(1);
            await fetch(`/api/tags/${targetId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: normalizedTarget })
            });
            if (otherIds.length > 0) {
                await apiPost("/api/tags/merge", { source_ids: otherIds, target_id: targetId });
            }
            showToast(`Merged ${selectedIds.length} tags into "${normalizedTarget}"`, "success");
        }
        tagManagerState.selectedTagIds.clear();
        document.getElementById("merge-dialog")?.classList.add("hidden");
        await loadAllTags();
        renderTagManager();
        if (fetchTagsFn) fetchTagsFn();
    } catch (error) { console.error(error); showToast("Failed to merge tags", "error"); }
}

export async function deleteTags(showToast, fetchTagsFn) {
    const selectedIds = Array.from(tagManagerState.selectedTagIds);
    if (selectedIds.length === 0) return;
    const selectedTags = tagManagerState.allTags.filter(t => selectedIds.includes(t.id));
    const tagNames = selectedTags.map(t => t.name).join(", ");
    if (!confirm(`Delete ${selectedIds.length} tags?\n${tagNames}\n\nThis will remove these tags from all items.`)) return;
    try {
        await Promise.all(selectedIds.map(id => fetch(`/api/tags/${id}`, { method: "DELETE" })));
        showToast(`Deleted ${selectedIds.length} tags`, "success");
        tagManagerState.selectedTagIds.clear();
        await loadAllTags();
        renderTagManager();
        if (fetchTagsFn) fetchTagsFn();
    } catch (error) { console.error(error); showToast("Failed to delete tags", "error"); }
}

export async function loadOrphanTags(showToast, fetchTagsFn) {
    try {
        const orphans = await apiGet('/api/tags/orphans');
        const orphanSection = document.getElementById('orphan-section');
        const orphanList = document.getElementById('orphan-list');
        if (orphanSection && orphanList) {
            if (orphans.length === 0) { orphanSection.classList.add('hidden'); return; }
            orphanSection.classList.remove('hidden');
            orphanList.innerHTML = orphans.slice(0, 50).map(t => `
                <span class="flex items-center gap-1 bg-white/5 border border-glass-border rounded px-2 py-0.5 text-xs">
                    <span class="text-amber-300">${t.name}</span>
                    <span class="text-text-muted">(${t.cnt ?? 0})</span>
                    <button class="orphan-del text-red-400 hover:text-red-300 ml-1" data-id="${t.id}" data-name="${t.name}" title="Delete tag">&times;</button>
                </span>
            `).join('');
            const toggleBtn = document.getElementById('orphan-toggle');
            if (toggleBtn) {
                toggleBtn.onclick = () => {
                    orphanList.classList.toggle('hidden');
                    toggleBtn.textContent = orphanList.classList.contains('hidden') ? 'Show' : 'Hide';
                };
            }
            orphanList.querySelectorAll('.orphan-del').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const tagId = parseInt(btn.dataset.id);
                    const name = btn.dataset.name;
                    if (confirm(`Delete orphan tag "${name}"?`)) {
                        try {
                            await apiDelete(`/api/tags/${tagId}`);
                            btn.closest('span').remove();
                            if (showToast) showToast(`Orphan tag "${name}" deleted`, 'success');
                            if (fetchTagsFn) fetchTagsFn();
                        } catch (e) { if (showToast) showToast('Delete failed', 'error'); }
                    }
                });
            });
        }
    } catch (e) { console.error('Orphan tags load failed', e); }
}
