// ── Obsidian Frost — Theme & Display Controller ──
// Handles theme switcher, compact mode, and focus mode HUD.

import { state } from './state.js';
import { dom } from './dom.js';
import { showToast } from './toast.js';
import { applyGridScale } from './filters.js';

export const THEMES = {
    "": { label: "Obsidian Frost" },
    "highcontrast": { label: "High Contrast" },
    "silver-charcoal": { label: "Silver Charcoal" },
    "cmyk": { label: "CMYK" },
    "github-dark": { label: "GitHub Style" },
    "glass-dark": { label: "Glass Dark" },
    "glass-light": { label: "Glass Light" },
    "flat-dark": { label: "Flat Dark" },
    "flat-light": { label: "Flat Light" },
    "macos-sequoia": { label: "macOS Sequoia" },
    "obsidian": { label: "✦ Obsidian" },
    "aurora": { label: "✦ Aurora" },
};

let activeTheme = localStorage.getItem('activeTheme') || '';
let compactMode = localStorage.getItem('compactMode') === '1';

export function applyTheme(theme) {
    activeTheme = theme;
    if (theme) {
        document.documentElement.setAttribute('data-theme', theme);
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem('activeTheme', theme);
    document.querySelectorAll('.theme-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === theme);
    });
}

export function applyCompactMode() {
    document.body.classList.toggle('compact-mode', compactMode);
    const btn = document.getElementById('compact-toggle');
    if (btn) {
        btn.classList.toggle('text-primary', compactMode);
        btn.classList.toggle('text-text-muted', !compactMode);
    }
}

export function toggleFocusMode() {
    state.focusMode = !state.focusMode;
    localStorage.setItem('focusMode', state.focusMode ? '1' : '0');
    document.getElementById('advanced-filters-bar')?.classList.remove('focus-float');
    document.body.classList.toggle('focus-mode', state.focusMode);
    if (state.focusMode) syncFocusHud();
    showToast(state.focusMode ? 'Focus mode ON — press F2 to exit' : 'Focus mode OFF');
}

export function syncFocusHud() {
    const focusSearch = document.getElementById('focus-search-input');
    if (focusSearch && dom.searchInput) focusSearch.value = dom.searchInput.value;
    const focusSlider = document.getElementById('focus-grid-scale');
    if (focusSlider && dom.gridScale) focusSlider.value = dom.gridScale.value;
    const focusSort = document.getElementById('focus-sort-select');
    if (focusSort) focusSort.value = state.sortBy || 'newest';
    if (dom.gridScale) applyGridScale(dom.gridScale.value);
}

export function initThemeController(onFetchItems) {
    applyTheme(activeTheme);
    applyCompactMode();

    const themeBtn = document.getElementById('theme-btn');
    const themeMenu = document.getElementById('theme-menu');
    if (themeBtn && themeMenu) {
        themeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const rect = themeBtn.getBoundingClientRect();
            themeMenu.style.top = (rect.bottom + 4) + 'px';
            themeMenu.style.right = (window.innerWidth - rect.right) + 'px';
            themeMenu.style.left = 'auto';
            themeMenu.classList.toggle('hidden');
        });
        themeMenu.querySelectorAll('.theme-option').forEach(opt => {
            opt.addEventListener('click', (e) => {
                e.stopPropagation();
                applyTheme(opt.dataset.theme);
                themeMenu.classList.add('hidden');
                showToast(`Theme: ${THEMES[opt.dataset.theme]?.label || 'Default'}`);
            });
        });
        document.addEventListener('click', (e) => {
            if (!themeMenu.contains(e.target) && e.target !== themeBtn) {
                themeMenu.classList.add('hidden');
            }
        });
    }

    const compactToggleBtn = document.getElementById('compact-toggle');
    if (compactToggleBtn) {
        compactToggleBtn.addEventListener('click', () => {
            compactMode = !compactMode;
            localStorage.setItem('compactMode', compactMode ? '1' : '0');
            applyCompactMode();
            showToast(compactMode ? 'Compact mode ON' : 'Compact mode OFF');
        });
    }

    // Focus mode bindings
    if (state.focusMode) {
        document.body.classList.add('focus-mode');
        syncFocusHud();
    }

    const focusBtn = document.getElementById('focus-mode-btn');
    const focusExitBtn = document.getElementById('focus-exit-btn');
    if (focusBtn) focusBtn.addEventListener('click', toggleFocusMode);
    if (focusExitBtn) focusExitBtn.addEventListener('click', toggleFocusMode);

    const focusSearchInput = document.getElementById('focus-search-input');
    if (focusSearchInput) {
        let focusSearchTimer;
        focusSearchInput.addEventListener('input', (e) => {
            if (dom.searchInput) dom.searchInput.value = e.target.value;
            state.searchQuery = e.target.value;
            if (dom.searchClear) dom.searchClear.classList.toggle('hidden', !e.target.value);
            clearTimeout(focusSearchTimer);
            focusSearchTimer = setTimeout(onFetchItems, 300);
        });
        focusSearchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                clearTimeout(focusSearchTimer);
                onFetchItems();
            }
            if (e.key === 'Escape') toggleFocusMode();
        });
    }

    const focusGridSlider = document.getElementById('focus-grid-scale');
    if (focusGridSlider) {
        focusGridSlider.addEventListener('input', (e) => applyGridScale(e.target.value));
    }

    const focusSortSel = document.getElementById('focus-sort-select');
    if (focusSortSel) {
        focusSortSel.addEventListener('change', (e) => {
            state.sortBy = e.target.value;
            if (dom.sortSelect) dom.sortSelect.value = e.target.value;
            onFetchItems();
        });
    }
}
