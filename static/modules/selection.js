// ── Selection Module ──
import { state } from './state.js';
import { dom } from './dom.js';

export function toggleSelection(id) {
    if (state.selectedIds.has(id)) state.selectedIds.delete(id);
    else state.selectedIds.add(id);
    updateSelectionUI();
}

export function clearSelection() {
    state.selectedIds.clear();
    updateSelectionUI();
}

export function selectAllOnPage() {
    state.items.forEach(item => state.selectedIds.add(item.id));
    updateSelectionUI();
}

export function updateSelectionUI() {
    dom.grid.querySelectorAll(".gallery-card").forEach(card => {
        const id = parseInt(card.dataset.id);
        const isSelected = state.selectedIds.has(id);
        card.classList.toggle("ring-2", isSelected);
        card.classList.toggle("ring-primary", isSelected);
        card.classList.toggle("ring-offset-2", isSelected);
        card.classList.toggle("ring-offset-void", isSelected);
    });
    if (state.selectedIds.size > 0) {
        dom.actionBar.classList.add("visible");
        dom.actionCount.textContent = `${state.selectedIds.size} selected`;
    } else {
        dom.actionBar.classList.remove("visible");
    }
}

export async function copySelectedLinks(showToast) {
    const links = state.items.filter(i => state.selectedIds.has(i.id) && i.gdrive_link).map(i => i.gdrive_link);
    if (!links.length) { showToast("No GDrive links in selection"); return; }
    try {
        await navigator.clipboard.writeText(links.join("\n"));
    } catch { /* fallback */ }
    showToast(`Copied ${links.length} GDrive link(s)`);
}
