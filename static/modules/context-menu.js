// ── Obsidian Frost — Context Menu Controller ──
// Handles right-click context menu on asset cards.

import { state } from './state.js';
import { dom } from './dom.js';

export function showContextMenu(x, y, itemId) {
    if (itemId) state.contextItemId = itemId;
    const isFav = state.favoriteIds.has(state.contextItemId);
    if (dom.ctxFavorite) dom.ctxFavorite.textContent = isFav ? "Remove Favorite" : "Add to Favorites";
    if (dom.contextMenu) {
        dom.contextMenu.style.left = `${x}px`;
        dom.contextMenu.style.top = `${y}px`;
        dom.contextMenu.classList.remove("hidden");
    }
}

export function initContextMenu(deps) {
    const { toggleFavorite, refreshVisibleFavStars, openCollectionPicker, openCollectionModal, collDeps } = deps;

    document.addEventListener("click", () => {
        if (dom.contextMenu) dom.contextMenu.classList.add("hidden");
    });

    if (dom.ctxFavorite) {
        dom.ctxFavorite.addEventListener("click", async () => {
            await toggleFavorite(state.contextItemId);
            refreshVisibleFavStars();
        });
    }

    if (dom.ctxCollections) {
        dom.ctxCollections.addEventListener("click", () => {
            const prev = state.selectedIds;
            state.selectedIds = new Set([state.contextItemId]);
            openCollectionPicker(deps.showToast, () => deps.renderCollectionPicker(collDeps()));
            state.selectedIds = prev;
        });
    }

    if (dom.ctxNewCollection) {
        dom.ctxNewCollection.addEventListener("click", () => openCollectionModal(true, collDeps()));
    }
}
