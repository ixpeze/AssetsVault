/**
 * thumbnails.js — lazy thumbnail loading via IntersectionObserver.
 *
 * Usage:
 *   import { initThumbnailObserver, requestThumbnail } from './thumbnails.js';
 *   initThumbnailObserver();           // call once in init()
 *   requestThumbnail(itemId, imgEl);   // called by card renderer
 *
 * Card images that have [data-item-id] will be observed automatically.
 * When they enter the viewport, the loader swaps src to /thumbnails/256/{itemId}.
 * On error, the original src is kept (graceful fallback via native onerror).
 *
 * PERF: No HEAD requests — we set src directly and rely on the browser's
 * native error handling to fall back if the thumbnail doesn't exist.
 */

const DEFAULT_SIZE = 256;

/** @type {IntersectionObserver | null} */
let _observer = null;

/** Cache of {itemId -> thumbUrl} to avoid duplicate swaps */
const _cache = new Map();

/**
 * Request a thumbnail for a given item, updating the img element.
 * Sets src directly to the thumbnail endpoint — no HEAD preflight.
 * @param {number} itemId
 * @param {HTMLImageElement} imgEl
 * @param {number} [size=256]
 */
export function requestThumbnail(itemId, imgEl, size = DEFAULT_SIZE) {
    if (!imgEl || !itemId) return;

    // Check local cache first
    const cached = _cache.get(itemId);
    if (cached) {
        imgEl.src = cached;
        return;
    }

    const thumbUrl = `/thumbnails/${size}/${itemId}`;
    const originalSrc = imgEl.src;

    // Store the original src for fallback
    imgEl.onerror = () => {
        // Thumbnail doesn't exist — revert to original and stop retrying
        imgEl.onerror = null;
        if (originalSrc && originalSrc !== thumbUrl) {
            imgEl.src = originalSrc;
        }
    };

    // Cache and swap
    _cache.set(itemId, thumbUrl);
    if (imgEl.isConnected) {
        imgEl.src = thumbUrl;
    }
}

/**
 * Observe an img element. When it enters the viewport, request its thumbnail.
 * Expects the element to have a data-item-id attribute.
 * @param {HTMLImageElement} imgEl
 */
export function observeImage(imgEl) {
    if (_observer && imgEl.dataset.itemId) {
        _observer.observe(imgEl);
    }
}

/**
 * Initialize the IntersectionObserver for lazy thumbnail loading.
 * Call once during app init. Safe to call multiple times (idempotent).
 */
export function initThumbnailObserver() {
    if (_observer) return;  // Already initialized

    if (!('IntersectionObserver' in window)) {
        // Browser doesn't support IntersectionObserver — skip silently
        return;
    }

    _observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            const imgEl = entry.target;
            const itemId = parseInt(imgEl.dataset.itemId, 10);
            if (!isNaN(itemId)) {
                requestThumbnail(itemId, imgEl, DEFAULT_SIZE);
            }
            _observer.unobserve(imgEl);  // Only load once
        }
    }, {
        rootMargin: '200px',  // Start loading 200px before entering viewport
        threshold: 0,
    });

    // Observe any card images already in the DOM
    document.querySelectorAll('img[data-item-id]').forEach(img => _observer.observe(img));
}
