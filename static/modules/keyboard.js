// ── Keyboard Navigation Module ──
// Provides vim-style spatial navigation, shortcut help overlay, and
// keyboard-first interactions for the gallery. Public-facing safe:
// all shortcuts are discoverable via the '?' help overlay.

import { state } from './state.js';

// ── Internal State ──
let focusedIndex = -1; // index into state.items
let columnsCount = 4;  // updated on resize
let helpOverlayOpen = false;

// ── Column Tracking ──
export function updateColumnCount() {
    const grid = document.getElementById('gallery-grid');
    if (!grid || !state.items.length) return;
    const cards = grid.querySelectorAll('.gallery-card');
    if (cards.length < 2) return;
    const firstTop = cards[0].getBoundingClientRect().top;
    let cols = 1;
    for (let i = 1; i < cards.length; i++) {
        if (cards[i].getBoundingClientRect().top !== firstTop) break;
        cols++;
    }
    columnsCount = cols;
}

// ── Focus Card ──
export function focusCard(index) {
    const grid = document.getElementById('gallery-grid');
    if (!grid) return;
    const cards = grid.querySelectorAll('.gallery-card');
    // remove old focus ring
    cards.forEach(c => c.classList.remove('kb-focused'));
    if (index < 0 || index >= state.items.length) { focusedIndex = -1; return; }
    focusedIndex = index;
    if (cards[index]) {
        cards[index].classList.add('kb-focused');
        cards[index].scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
}

export function getFocusedIndex() { return focusedIndex; }
export function clearFocus() { focusCard(-1); }

// ── Help Overlay ──
function createHelpOverlay() {
    const el = document.createElement('div');
    el.id = 'kb-help-overlay';
    el.innerHTML = `
        <div id="kb-help-backdrop" class="fixed inset-0 bg-black/70 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
            <div class="bg-[#0a0a0a] border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden">
                <div class="flex items-center justify-between px-6 py-4 border-b border-white/10">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-primary text-xl">keyboard</span>
                        <h2 class="font-display font-semibold text-white text-base">Keyboard Shortcuts</h2>
                    </div>
                    <button id="kb-help-close" class="text-text-muted hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-xl">close</span>
                    </button>
                </div>
                <div class="p-6 grid grid-cols-2 gap-x-8 gap-y-1.5 max-h-[70vh] overflow-y-auto">
                    ${renderShortcutSection('Navigation', [
                        ['j / ↓', 'Next card'],
                        ['k / ↑', 'Previous card'],
                        ['h / ←', 'Card left'],
                        ['l / →', 'Card right'],
                        ['g g', 'Scroll to top'],
                        ['G', 'Scroll to bottom'],
                    ])}
                    ${renderShortcutSection('Actions', [
                        ['Enter / Space', 'Open in lightbox'],
                        ['f', 'Toggle favorite'],
                        ['x', 'Toggle selection'],
                        ['Ctrl+A', 'Select all on page'],
                        ['Esc', 'Clear selection / close'],
                    ])}
                    ${renderShortcutSection('Search & Views', [
                        ['/', 'Focus search bar'],
                        ['F2', 'Toggle focus mode'],
                        ['?', 'Show this overlay'],
                    ])}
                    ${renderShortcutSection('Lightbox', [
                        ['← / ↑', 'Previous item'],
                        ['→ / ↓', 'Next item'],
                        ['f', 'Toggle favorite'],
                        ['Esc', 'Close lightbox'],
                    ])}
                </div>
                <div class="px-6 py-3 border-t border-white/10 text-center text-xs text-text-muted font-mono">
                    Press <kbd class="px-1.5 py-0.5 bg-white/10 rounded text-white">?</kbd> anytime to toggle this overlay
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(el);
    document.getElementById('kb-help-close')?.addEventListener('click', closeHelpOverlay);
    document.getElementById('kb-help-backdrop')?.addEventListener('click', (e) => {
        if (e.target === document.getElementById('kb-help-backdrop')) closeHelpOverlay();
    });
}

function renderShortcutSection(title, shortcuts) {
    return `
        <div class="col-span-2 mt-3 mb-1 first:mt-0">
            <div class="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2">${title}</div>
        </div>
        ${shortcuts.map(([key, desc]) => `
            <div class="flex items-center justify-between py-1">
                <kbd class="text-xs font-mono bg-white/8 border border-white/10 rounded px-2 py-0.5 text-white whitespace-nowrap">${key}</kbd>
                <span class="text-xs text-text-muted text-right ml-2">${desc}</span>
            </div>
        `).join('')}
    `;
}

export function openHelpOverlay() {
    helpOverlayOpen = true;
    const existing = document.getElementById('kb-help-overlay');
    if (!existing) createHelpOverlay();
    else document.getElementById('kb-help-overlay').classList.remove('hidden');
}

export function closeHelpOverlay() {
    helpOverlayOpen = false;
    const el = document.getElementById('kb-help-overlay');
    if (el) el.classList.add('hidden');
}

export function toggleHelpOverlay() {
    if (helpOverlayOpen) closeHelpOverlay();
    else openHelpOverlay();
}

// ── g g detection ──
let lastGTime = 0;

// ── Main Keyboard Handler — Gallery Mode ──
// Call this from init.js, BEFORE the existing keydown handler,
// only when lightbox is closed.
export function handleGalleryKey(e, deps) {
    const { openLightbox, toggleFavorite, toggleSelection, updateSelectionUI, fetchItems } = deps;

    // '?' shortcut — works even in input fields
    if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        toggleHelpOverlay();
        return;
    }

    // Guard: skip navigation keys when typing in inputs
    const tag = document.activeElement.tagName;
    const isEditable = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
        || document.activeElement.isContentEditable;
    if (isEditable) return;

    // Skip if modifiers (except Shift for G)
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    const total = state.items.length;
    if (total === 0) return;

    switch (e.key) {
        case 'j':
        case 'ArrowDown': {
            e.preventDefault();
            updateColumnCount();
            const next = focusedIndex < 0 ? 0 : Math.min(focusedIndex + columnsCount, total - 1);
            focusCard(next);
            break;
        }
        case 'k':
        case 'ArrowUp': {
            e.preventDefault();
            updateColumnCount();
            const prev = focusedIndex < 0 ? 0 : Math.max(focusedIndex - columnsCount, 0);
            focusCard(prev);
            break;
        }
        case 'h':
        case 'ArrowLeft': {
            e.preventDefault();
            const left = focusedIndex <= 0 ? 0 : focusedIndex - 1;
            focusCard(left);
            break;
        }
        case 'l':
        case 'ArrowRight': {
            e.preventDefault();
            const right = focusedIndex < 0 ? 0 : Math.min(focusedIndex + 1, total - 1);
            focusCard(right);
            break;
        }
        case 'Enter':
        case ' ': {
            e.preventDefault();
            if (focusedIndex >= 0) openLightbox(focusedIndex);
            break;
        }
        case 'f': {
            if (focusedIndex >= 0) {
                const item = state.items[focusedIndex];
                if (item) toggleFavorite(item.id);
            }
            break;
        }
        case 'x': {
            if (focusedIndex >= 0) {
                const item = state.items[focusedIndex];
                if (item) { toggleSelection(item.id); updateSelectionUI(); }
            }
            break;
        }
        case 'g': {
            const now = Date.now();
            if (now - lastGTime < 500) {
                // g g — scroll to top
                e.preventDefault();
                const sc = document.getElementById('scroll-container');
                if (sc) sc.scrollTo({ top: 0, behavior: 'smooth' });
                focusCard(0);
                lastGTime = 0;
            } else {
                lastGTime = now;
            }
            break;
        }
        case 'G': {
            e.preventDefault();
            const sc = document.getElementById('scroll-container');
            if (sc) sc.scrollTo({ top: sc.scrollHeight, behavior: 'smooth' });
            focusCard(total - 1);
            break;
        }
        default:
            break;
    }
}

// ── Inject focus ring CSS ──
(function injectKeyboardStyles() {
    const s = document.createElement('style');
    s.textContent = `
        .gallery-card.kb-focused {
            outline: 2px solid var(--color-primary, #3780f6);
            outline-offset: 2px;
            border-radius: 6px;
        }
        #kb-help-overlay.hidden { display: none !important; }
        #kb-help-overlay kbd {
            font-family: 'JetBrains Mono', monospace;
        }
    `;
    document.head.appendChild(s);
})();
