// ── Favorites Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { apiPost } from './api.js';

export async function toggleFavorite(itemId) {
    try {
        const data = await apiPost("/api/favorites/toggle", { item_id: itemId });
        if (data.favorited) {
            state.favoriteIds.add(itemId);
        } else {
            state.favoriteIds.delete(itemId);
        }
        dom.favCount.textContent = state.favoriteIds.size;
        return data.favorited;
    } catch (err) {
        console.error("Toggle favorite failed:", err);
        return null;
    }
}

export async function fetchFavoriteIds() {
    try {
        const ids = await (await fetch("/api/favorites/ids")).json();
        state.favoriteIds = new Set(ids);
        dom.favCount.textContent = state.favoriteIds.size;
    } catch (err) {
        console.error("Failed to fetch favorites:", err);
    }
}

export function refreshVisibleFavStars() {
    dom.grid.querySelectorAll(".fav-btn").forEach(btn => {
        const id = parseInt(btn.dataset.id);
        const isFav = state.favoriteIds.has(id);
        const icon = btn.querySelector("span");
        btn.classList.toggle("bg-[#F59E0B]/20", isFav);
        btn.classList.toggle("text-[#F59E0B]", isFav);
        btn.classList.toggle("bg-black/40", !isFav);
        btn.classList.toggle("text-white/40", !isFav);
        icon.style.fontVariationSettings = isFav ? '"FILL" 1' : '';
    });
}

export async function favoriteAllSelected(showToast) {
    const toFav = [...state.selectedIds].filter(id => !state.favoriteIds.has(id));
    await Promise.all(toFav.map(id => toggleFavorite(id)));
    refreshVisibleFavStars();
    showToast(`Favorited ${toFav.length} item(s)`);
}
