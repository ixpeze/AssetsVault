// ── Filters Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { renderVirtualGrid } from './grid.js';

export function applyFilters(fetchItems) {
    state.advancedFilters.hasGdrive = document.getElementById("filter-gdrive").value;
    state.advancedFilters.hasImage = document.getElementById("filter-image").value;
    state.advancedFilters.tier = document.getElementById("filter-tier").value;
    state.advancedFilters.hasSize = document.getElementById("filter-size").value;
    const rEl = document.getElementById("filter-render");
    if (rEl) state.advancedFilters.render = rEl.value;
    const mEl = document.getElementById("filter-max-version");
    if (mEl) state.advancedFilters.maxVersion = mEl.value;

    const activeCount = Object.values(state.advancedFilters).filter(v => v !== "").length;
    const badge = document.getElementById("active-filters-badge");
    const clearBtn = document.getElementById("filters-clear");

    badge.textContent = activeCount;
    badge.classList.toggle("hidden", activeCount === 0);
    clearBtn.classList.toggle("hidden", activeCount === 0);

    fetchItems();
}

// ── Base card width at scale=1.0 ──
const BASE_CARD_WIDTH = 280;
const CARD_GAP = 24; // 1.5rem = 24px at 16px base

export function applyGridScale(scale) {
    const numericScale = parseFloat(scale);

    // ── Sync sliders & localStorage ──
    dom.gridScale.value = scale;
    const focusSlider = document.getElementById('focus-grid-scale');
    if (focusSlider) focusSlider.value = scale;
    localStorage.setItem("gridScale", scale);

    // ── Highlight preset buttons ──
    document.querySelectorAll(".grid-preset").forEach(btn => {
        const btnScale = parseFloat(btn.dataset.scale);
        if (Math.abs(btnScale - numericScale) < 0.05) {
            btn.className = "grid-preset px-2 py-1 text-[10px] border rounded transition-colors bg-primary/20 border-primary/40 text-primary";
        } else {
            btn.className = "grid-preset px-2 py-1 text-[10px] border border-glass-border rounded hover:bg-white/10 transition-colors";
        }
    });

    // ── Determine named size mode for CSS targeting ──
    let sizeMode;
    if (numericScale >= 2.0) sizeMode = 'xl';
    else if (numericScale >= 1.2) sizeMode = 'l';
    else if (numericScale >= 0.8) sizeMode = 'm';
    else if (numericScale >= 0.5) sizeMode = 's';
    else sizeMode = 'xs'; // Ultra-compact
    dom.grid.dataset.size = sizeMode;

    // ── Compute exact column count from available container width ──
    renderVirtualGrid(true);
}

/**
 * Recalculate columns proxy for compatibility.
 */
export function recalcColumns() {
    renderVirtualGrid();
}

export function setTierFilter(tier, rebuildFilteredTree, fetchItems) {
    state.activeTier = tier;
    [dom.pillAll, dom.pillFree, dom.pillPaid].forEach(el => {
        el.className = "flex-1 py-1 text-[10px] font-bold uppercase tracking-wider rounded text-text-muted hover:text-white transition-colors";
    });
    const target = tier === "" ? dom.pillAll : (tier === "Free" ? dom.pillFree : dom.pillPaid);
    target.className = `flex-1 py-1 text-[10px] font-bold uppercase tracking-wider rounded bg-primary/20 text-primary transition-colors`;
    rebuildFilteredTree();
    fetchItems();
}

export function updateFooter(state) {
    dom.paginationInfo.textContent = state.total > 0
        ? `${state.items.length} of ${state.total} assets loaded`
        : "No assets";
    dom.resultsCountBadge.textContent = `${state.total} ITEMS`;
    dom.statTotalItems.textContent = state.total;
}

export function renderSkeleton() {
    dom.grid.innerHTML = Array.from({ length: 10 }, (_, i) => `
        <div class="rounded-xl overflow-hidden border border-glass-border break-inside-avoid mb-5" style="animation-delay: ${i * 40}ms">
            <div class="skeleton" style="height: ${180 + (i % 3) * 60}px"></div>
            <div class="p-3 space-y-2">
                <div class="skeleton h-2.5 rounded w-1/4"></div>
                <div class="skeleton h-3.5 rounded w-3/4"></div>
            </div>
        </div>`).join("");
}
