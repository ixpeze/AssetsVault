// ── Card Rendering Module ──
import { state } from './state.js';
import { dom } from './dom.js';

// HTML entity map for common entities — avoids DOM element creation
const _ENTITY_MAP = {
    '&amp;': '&', '&lt;': '<', '&gt;': '>',
    '&quot;': '"', '&#039;': "'", '&#39;': "'",
    '&nbsp;': ' ', '&#x27;': "'", '&#x2F;': '/',
};
const _ENTITY_RE = /&(?:amp|lt|gt|quot|nbsp|#0?39|#x27|#x2F);/gi;

export function cleanTitle(html) {
    if (!html) return '';
    // Fast path: no entities present
    if (html.indexOf('&') === -1) return html;
    // Replace known entities without creating DOM nodes
    let result = html.replace(_ENTITY_RE, m => _ENTITY_MAP[m.toLowerCase()] || m);
    // Strip any remaining HTML tags
    return result.replace(/<[^>]*>/g, '');
}

export function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, '&#96;');
}

export function buildCategoryTree(flatCategories) {
    const map = {};
    const roots = [];
    const nameToId = {};
    flatCategories.forEach(c => { nameToId[c.name.trim().toLowerCase()] = c.id; });

    flatCategories.forEach(c => {
        const node = { ...c, children: [], item_count: c.scraped_count || 0 };
        if ((!node.parent_id || node.parent_id === 0) && node.name.includes(" - ")) {
            const parts = node.name.split(/\s+-\s+/);
            if (parts.length >= 2) {
                const parentName = parts[0].trim();
                const virtualParentId = nameToId[parentName.toLowerCase()];
                if (virtualParentId && virtualParentId !== node.id) {
                    node.parent_id = virtualParentId;
                    node.name = parts.slice(1).join(" - ").trim();
                    if (node.name === node.name.toUpperCase() && node.name.length > 3) {
                        node.name = node.name.charAt(0) + node.name.slice(1).toLowerCase();
                    }
                }
            }
        }
        map[node.id] = node;
    });

    Object.values(map).forEach(node => {
        if (node.parent_id && node.parent_id !== 0 && map[node.parent_id]) {
            map[node.parent_id].children.push(node);
        } else {
            roots.push(node);
        }
    });

    const processNode = (node) => {
        node.children.forEach(processNode);
        node.item_count += node.children.reduce((sum, child) => sum + child.item_count, 0);
        node.children.sort((a, b) => a.name.localeCompare(b.name));
    };
    roots.forEach(processNode);
    roots.sort((a, b) => a.name.localeCompare(b.name));
    return roots.filter(node => node.item_count > 0);
}

export function buildCardHTML(item, idx) {
    const title = cleanTitle(item.title);
    const titleText = escapeHtml(title);
    const titleAttr = escapeAttr(title);
    const imgSrc = item.thumbnail_url || item.thumbnail_url_256 || item.local_image_url || item.image_url || "";
    const fallbackSrc = item.local_image_url || item.image_url || "";
    const imgSrcAttr = escapeAttr(imgSrc);
    const fallbackSrcAttr = escapeAttr(fallbackSrc);
    const hasImage = !!imgSrc;
    const sizeDisplay = item.file_size ? ` • ${formatBytes(item.file_size)}` : '';
    const categoryDisplay = escapeHtml(item.category_slug ? item.category_slug.replace(/-/g, " ") : "Uncategorized") + sizeDisplay;
    const isFav = state.favoriteIds.has(item.id);
    const isSelected = state.selectedIds.has(item.id);

    const isPaid = item.tier === 'Paid';
    const dotColor = isPaid ? 'bg-[#F59E0B]' : 'bg-[#4ADE80]';
    const dotGlow = isPaid ? 'shadow-[0_0_6px_rgba(245,158,11,0.6)]' : 'shadow-[0_0_6px_rgba(74,222,128,0.5)]';
    const tierBadge = `<div class="absolute top-2.5 left-2.5 z-10 pointer-events-none"><div class="w-2.5 h-2.5 rounded-full ${dotColor} ${dotGlow} border border-white/20" title="${item.tier || 'Free'}"></div></div>`;

    const favActiveClass = isFav ? 'fav-btn active' : 'fav-btn';
    const favBtn = `<button class="${favActiveClass} absolute top-2 right-2 z-10 flex items-center justify-center w-7 h-7 rounded-full ${isFav ? 'bg-[#F59E0B]/20 text-[#F59E0B]' : 'bg-black/40 text-white/40 hover:text-[#F59E0B]'} backdrop-blur-sm transition-all" data-id="${item.id}"><span class="material-symbols-outlined text-[18px]" style="${isFav ? 'font-variation-settings: "FILL" 1' : ''}">${isFav ? 'star' : 'star'}</span></button>`;

    const selectedClass = isSelected ? 'selected' : '';

    const gdriveBtn = item.gdrive_link
        ? `<a href="${escapeAttr(item.gdrive_link)}" target="_blank" rel="noopener" class="flex items-center justify-center w-7 h-7 rounded border border-glass-border hover:bg-frost-hover text-text-muted hover:text-white transition-all" title="Google Drive"><span class="material-symbols-outlined text-[16px]">drive_file_move</span></a>`
        : `<button class="flex items-center justify-center w-7 h-7 rounded border border-glass-border opacity-30 cursor-not-allowed text-text-muted"><span class="material-symbols-outlined text-[16px]">drive_file_move</span></button>`;

    const mirrorBtn = item.mirror_link
        ? `<a href="${escapeAttr(item.mirror_link)}" target="_blank" rel="noopener" class="flex items-center justify-center w-7 h-7 rounded border border-glass-border hover:bg-frost-hover text-text-muted hover:text-white transition-all" title="Mirror"><span class="material-symbols-outlined text-[16px]">cloud_download</span></a>`
        : "";

    const sourceBtn = item.post_url
        ? `<a href="${escapeAttr(item.post_url)}" target="_blank" rel="noopener" class="flex items-center justify-center w-7 h-7 rounded border border-glass-border hover:bg-frost-hover text-text-muted hover:text-white transition-all" title="Source"><span class="material-symbols-outlined text-[16px]">open_in_new</span></a>`
        : "";

    const downloadUrl = item.gdrive_link || item.mirror_link || '';
    const hasDownloadUrl = !!downloadUrl;
    const activeJob = null;

    let downloadBtn = '';
    if (hasDownloadUrl) {
        downloadBtn = `<button class="download-btn flex items-center justify-center w-7 h-7 rounded border border-glass-border hover:bg-frost-hover text-text-muted hover:text-white transition-all" data-id="${item.id}" data-download-url="${escapeAttr(downloadUrl)}" data-download-state="online" title="Download with client app"><span class="material-symbols-outlined text-[16px]">download_for_offline</span></button>`;
    }

    // Build downloading overlay if active
    let overlayHTML = '';
    let overlayHiddenClass = 'hidden';
    if (activeJob) {
        overlayHiddenClass = '';
        const speed = activeJob.speed_kbps > 1024 
            ? `${(activeJob.speed_kbps / 1024).toFixed(1)} MB/s` 
            : `${activeJob.speed_kbps} KB/s`;
        const totalStr = activeJob.total_bytes > 0 ? formatBytes(activeJob.total_bytes) : '';
        const bytesWrittenStr = activeJob.bytes_written > 0 ? formatBytes(activeJob.bytes_written) : '';

        if (activeJob.status === 'pending') {
            overlayHTML = `
                <div class="flex flex-col items-center gap-1 bg-black/70 backdrop-blur-sm px-3 py-2 rounded-lg border border-primary/30">
                    <div class="flex items-center gap-1.5 text-primary text-[11px] font-medium">
                        <span class="material-symbols-outlined text-[14px] animate-pulse">hourglass_top</span>
                        <span>Queued</span>
                    </div>
                </div>
            `;
        } else {
            overlayHTML = `
                <div class="flex flex-col items-center gap-1 bg-black/70 backdrop-blur-sm px-3 py-2 rounded-lg border border-primary/30">
                    <div class="flex items-center gap-1.5 text-primary text-[11px] font-medium">
                        <span class="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                        <span>${activeJob.progress}%</span>
                        <span class="text-text-muted text-[9px]">${speed}</span>
                    </div>
                    <div class="w-full bg-white/10 rounded-full h-1 overflow-hidden" style="min-width: 80px">
                        <div class="h-full bg-primary rounded-full transition-all duration-300" style="width: ${activeJob.progress}%"></div>
                    </div>
                    ${totalStr ? `<span class="text-text-muted text-[8px] font-mono">${bytesWrittenStr} / ${totalStr}</span>` : ''}
                </div>
            `;
        }
    }

    return `<div class="group gallery-card relative isolate flex flex-col bg-frost border border-glass-border rounded overflow-hidden cursor-pointer ${selectedClass}" data-index="${idx}" data-id="${item.id}">
        <div class="card-thumb w-full overflow-hidden relative bg-[#111]">
            ${tierBadge}${favBtn}
            <div class="download-overlay absolute inset-0 z-20 flex items-center justify-center pointer-events-none ${overlayHiddenClass}">${overlayHTML}</div>
            ${hasImage
            ? `<div class="img-placeholder aspect-[4/3]"><img class="w-full h-full object-cover opacity-0 transition-opacity duration-300 " src="${imgSrcAttr}" data-fallback-src="${fallbackSrcAttr}" alt="${titleAttr}" loading="lazy" onload="this.classList.add('opacity-100');this.parentElement.classList.remove('img-placeholder')" onerror="const f=this.dataset.fallbackSrc;if(f&&this.src!==f){this.onerror=null;this.src=f}else{this.parentElement.innerHTML='<div class=\\'flex items-center justify-center w-full h-full bg-[#151515] text-text-muted aspect-[4/3]\\'><span class=\\'material-symbols-outlined text-4xl opacity-20\\'>image_not_supported</span></div>'}"></div>`
            : `<div class="flex items-center justify-center w-full h-full bg-[#151515] text-text-muted aspect-[4/3]"><span class="material-symbols-outlined text-4xl opacity-20">image</span></div>`}
        </div>
        <div class="flex items-center justify-between p-3 bg-[#111]/80 border-t border-glass-border transition-colors">
            <div class="flex flex-col overflow-hidden flex-1">
                <span class="text-[9px] text-text-muted font-mono uppercase truncate mb-0.5">${categoryDisplay}</span>
                <h3 class="text-sm font-medium text-white truncate font-display" title="${titleAttr}">${titleText}</h3>
                ${(item.render_engine || item.max_version) ? `
                <div class="flex items-center gap-1 mt-1 overflow-hidden">
                    ${item.render_engine ? `<span class="px-1.5 py-0.2 rounded text-[8px] font-mono bg-primary/10 border border-primary/20 text-primary truncate max-w-[120px]" title="Render Engine">${escapeHtml(item.render_engine)}</span>` : ''}
                    ${item.max_version ? `<span class="px-1.5 py-0.2 rounded text-[8px] font-mono bg-white/5 border border-white/10 text-text-muted truncate" title="Max Version">${escapeHtml(item.max_version)}</span>` : ''}
                </div>` : ''}
                <div class="flex items-center gap-2 mt-1.5">${downloadBtn}${gdriveBtn}${mirrorBtn}${sourceBtn}</div>
            </div>
        </div>
    </div>`;
}

export function appendCards(items, startIdx) {
    const fragment = document.createDocumentFragment();
    const tempContainer = document.createElement('div');
    tempContainer.innerHTML = items.map((item, i) => buildCardHTML(item, startIdx + i)).join("");
    while (tempContainer.firstChild) {
        fragment.appendChild(tempContainer.firstChild);
    }
    dom.grid.appendChild(fragment);
}

/**
 * Initialize a single delegated event listener on the grid container.
 * Replaces per-card addEventListener calls — one listener handles all cards.
 * Call once during app init.
 */
let _delegationInitialized = false;
export function initCardDelegation({ openLightbox, toggleSelection, toggleFavorite, showContextMenu }) {
    if (_delegationInitialized) return;
    _delegationInitialized = true;

    dom.grid.addEventListener("click", (e) => {
        // Download button
        const dlBtn = e.target.closest(".download-btn");
        if (dlBtn) {
            e.stopPropagation();
            const id = parseInt(dlBtn.dataset.id);
            import('./downloader.js?v=4').then(m => m.enqueueDownload(id, dlBtn.dataset.downloadUrl || ''));
            return;
        }

        // Favorite button
        const favBtn = e.target.closest(".fav-btn");
        if (favBtn) {
            e.stopPropagation();
            const id = parseInt(favBtn.dataset.id);
            toggleFavorite(id).then(nowFav => {
                if (nowFav !== null) {
                    const icon = favBtn.querySelector("span");
                    if (nowFav) {
                        favBtn.classList.add("bg-[#F59E0B]/20", "text-[#F59E0B]");
                        favBtn.classList.remove("bg-black/40", "text-white/40");
                        icon.style.fontVariationSettings = '"FILL" 1';
                    } else {
                        favBtn.classList.remove("bg-[#F59E0B]/20", "text-[#F59E0B]");
                        favBtn.classList.add("bg-black/40", "text-white/40");
                        icon.style.fontVariationSettings = '';
                    }
                }
            });
            return;
        }

        // Skip other buttons / links
        if (e.target.closest("a") || e.target.closest("button")) return;

        // Card click
        const card = e.target.closest(".gallery-card");
        if (!card) return;
        if (e.ctrlKey || e.metaKey) {
            toggleSelection(parseInt(card.dataset.id));
            return;
        }
        openLightbox(parseInt(card.dataset.index));
    });

    dom.grid.addEventListener("contextmenu", (e) => {
        const card = e.target.closest(".gallery-card");
        if (!card) return;
        e.preventDefault();
        state.contextItemId = parseInt(card.dataset.id);
        showContextMenu(e.clientX, e.clientY);
    });
}

// Kept for backward compatibility — now a no-op since delegation handles everything
export function attachCardListeners() { }

export function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
        val /= 1024;
        i++;
    }
    return `${val.toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}
