// ── Taxonomy Tree Module ──
import { state } from './state.js';
import { dom } from './dom.js';

export function formatCount(n) {
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return n.toString();
}

let currentSetActiveTaxonomy = null;

export function renderTaxonomyTree() {
    if (!state.taxonomyTree || !state.taxonomyTree.length) {
        dom.categoryList.innerHTML = '<div class="px-3 py-2 text-sm text-text-muted">No categories</div>';
        return;
    }
    dom.categoryList.innerHTML = state.taxonomyTree
        .filter(g => g.item_count > 0)
        .map(g => renderTaxonomyGroup(g)).join("");
    attachTaxonomyListeners(currentSetActiveTaxonomy);
}

export function renderTaxonomyGroup(group) {
    const isExpanded = state.expandedCategories.has(group.id);
    const isActive = state.activeTaxonomy === group.slug;
    const hasChildren = group.children && group.children.length > 0;

    const arrowIcon = hasChildren
        ? `<span class="material-symbols-outlined text-[14px] text-text-muted transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}">chevron_right</span>`
        : '';

    const icon = group.icon || 'category';
    const countBadge = `<span class="text-[9px] font-mono opacity-40 bg-[#151515] px-1.5 rounded">${formatCount(group.item_count)}</span>`;

    let html = `<div class="taxonomy-group">
        <div class="tax-row group flex items-center gap-2 px-3 py-1.5 rounded text-xs cursor-pointer select-none transition-colors
            ${isActive ? 'text-white bg-white/10 font-medium' : 'text-text-muted hover:text-white hover:bg-white/5'}"
            data-slug="${group.slug}" data-id="${group.id}">
            <div class="tax-toggle shrink-0 flex items-center justify-center w-4 h-4 -ml-1 rounded hover:bg-white/10" data-id="${group.id}" data-has-children="${hasChildren}">
                ${arrowIcon}
            </div>
            <span class="material-symbols-outlined text-[16px] opacity-60">${icon}</span>
            <span class="truncate tax-name flex-1">${group.name}</span>
            ${countBadge}
        </div>`;

    if (hasChildren && isExpanded) {
        html += `<div class="tax-children pl-6 border-l border-white/5 ml-5 mt-0.5 space-y-0.5">`;
        group.children.forEach(child => {
            const childActive = state.activeTaxonomy === child.slug;
            html += `<div class="tax-row group flex items-center gap-2 px-3 py-1 rounded text-[11px] cursor-pointer select-none transition-colors
                ${childActive ? 'text-white bg-white/10 font-medium' : 'text-text-muted hover:text-white hover:bg-white/5'}"
                data-slug="${child.slug}" data-id="${child.id}">
                <span class="truncate tax-name flex-1">${child.name}</span>
                <span class="text-[9px] font-mono opacity-40 bg-[#151515] px-1.5 rounded">${formatCount(child.item_count)}</span>
            </div>`;
        });
        html += `</div>`;
    }
    return html + `</div>`;
}

export function attachTaxonomyListeners(setActiveTaxonomyFunc) {
    if (setActiveTaxonomyFunc) currentSetActiveTaxonomy = setActiveTaxonomyFunc;

    dom.categoryList.querySelectorAll(".tax-toggle").forEach(el => {
        el.addEventListener("click", (e) => {
            e.stopPropagation();
            const id = parseInt(el.dataset.id);
            if (el.dataset.hasChildren === "true") {
                state.expandedCategories.has(id) ? state.expandedCategories.delete(id) : state.expandedCategories.add(id);
                renderTaxonomyTree();
            }
        });
    });
    dom.categoryList.querySelectorAll(".tax-row").forEach(el => {
        el.addEventListener("click", (e) => {
            if (e.target.closest(".tax-toggle")) return;
            const slug = el.dataset.slug;
            const name = el.querySelector(".tax-name")?.textContent || slug;
            if (currentSetActiveTaxonomy) currentSetActiveTaxonomy(slug, name);
        });
    });
}

export function renderCategories() { renderTaxonomyTree(); }
