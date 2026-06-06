// ── Colors Module ──
import { state } from './state.js';
import { apiGet } from './api.js';

export async function fetchColors(fetchItems) {
    try {
        const colors = await apiGet("/api/colors");
        renderColors(colors, fetchItems);
    } catch (e) {
        console.error("Failed to fetch colors", e);
    }
}

export function renderColors(colors, fetchItems) {
    const container = document.getElementById("color-palette");
    const resetBtn = document.getElementById("color-reset");
    if (!container) return;
    container.innerHTML = "";

    colors.forEach(c => {
        const btn = document.createElement("button");
        btn.className = "w-3.5 h-3.5 rounded-full border border-white/10 hover:scale-125 hover:z-10 transition-transform cursor-pointer relative";
        btn.style.backgroundColor = c.hex;
        btn.title = `${c.name} (${c.cnt})`;

        if (state.activeColor === c.hex) {
            btn.classList.add("ring-2", "ring-white", "z-10", "scale-110");
        }

        btn.onclick = () => {
            if (state.activeColor === c.hex) {
                state.activeColor = "";
                btn.classList.remove("ring-2", "ring-white", "z-10", "scale-110");
                if (resetBtn) resetBtn.classList.add("hidden");
            } else {
                state.activeColor = c.hex;
                renderColors(colors, fetchItems);
                if (resetBtn) resetBtn.classList.remove("hidden");
            }
            fetchItems();
        };

        container.appendChild(btn);
    });

    if (resetBtn) {
        resetBtn.onclick = () => {
            state.activeColor = "";
            renderColors(colors, fetchItems);
            resetBtn.classList.add("hidden");
            fetchItems();
        };
        if (state.activeColor) resetBtn.classList.remove("hidden");
        else resetBtn.classList.add("hidden");
    }
}
