// ── Dashboard Tab System + Scraper Tree + Data Quality ──
// Phase 2.1 / 2.2 / 2.3

import { apiGet, apiPost } from './api.js';
import { showToast } from './toast.js';
import { chooseDownloadDirectory, loadSettings, saveSettings } from './settings.js';
import { loadDownloads, openDownloadsFolder } from './downloader.js?v=4';

// ── Tab State ──
let activeTab = 'overview';
let scraperTreeLoaded = false;
let qualityLoaded = false;

// ── Tab Switching ──
export function initDashboardTabs(deps) {
    const { updateDashboard, fetchAnalytics, loadDbHealth, loadCoverageHeatmap } = deps;

    document.querySelectorAll('.dash-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            switchTab(btn.dataset.tab, deps);
        });
    });

    // Save Settings button click handler
    document.getElementById('save-settings-btn')?.addEventListener('click', saveSettings);
    document.getElementById('choose-download-dir-btn')?.addEventListener('click', chooseDownloadDirectory);
    document.getElementById('open-downloads-folder-settings')?.addEventListener('click', openDownloadsFolder);

    // Vacuum button (shared between overview + quick actions)
    ['db-vacuum-btn', 'qa-vacuum-btn'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', async () => {
            if (!confirm('Vacuum and optimize the database? This may take a moment.')) return;
            try {
                await apiPost('/api/analytics/vacuum', {});
                showToast('Database vacuumed and optimized', 'success');
                loadDbHealth();
            } catch (e) { showToast('Vacuum failed', 'error'); }
        });
    });

    // FTS sync button
    document.getElementById('quality-fts-sync-btn')?.addEventListener('click', async () => {
        try {
            await apiPost('/api/admin/fts-sync', {});
            showToast('FTS resync queued — restart app to apply', 'success');
        } catch (e) { showToast('FTS sync failed', 'error'); }
    });
}

export function switchTab(tabName, deps) {
    activeTab = tabName;

    // Update tab button styles
    document.querySelectorAll('.dash-tab').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle('border-primary', isActive);
        btn.classList.toggle('text-white', isActive);
        btn.classList.toggle('border-transparent', !isActive);
        btn.classList.toggle('text-text-muted', !isActive);
    });

    // Show/hide panels
    document.querySelectorAll('.dash-panel').forEach(panel => {
        panel.classList.toggle('hidden', !panel.id.endsWith(tabName));
    });

    // Lazy-load tab data
    if (tabName === 'scraper' && !scraperTreeLoaded) {
        scraperTreeLoaded = true;
        loadScraperTree();
        initScraperTreeButtons(deps);
    }
    if (tabName === 'quality' && !qualityLoaded) {
        qualityLoaded = true;
        loadQualityData();
        initQualityButtons();
    }
    if (tabName === 'downloads') {
        loadDownloads();
        loadSettings();
    }
}

export function resetTabCache() {
    scraperTreeLoaded = false;
    qualityLoaded = false;
}

// ═══════════════════════════════════════════════════════════════
// SCRAPER TAB — 2.2
// ═══════════════════════════════════════════════════════════════

async function loadScraperTree() {
    const container = document.getElementById('scraper-tree-container');
    if (!container) return;
    try {
        const tree = await apiGet('/api/scraper/categories');
        renderScraperTree(tree, container);
    } catch (e) {
        container.innerHTML = '<div class="p-8 text-center text-red-400 text-sm">Failed to load category tree</div>';
        console.error('Scraper tree load failed', e);
    }
}

function renderScraperTree(nodes, container) {
    if (!nodes || nodes.length === 0) {
        container.innerHTML = '<div class="p-8 text-center text-text-muted text-sm italic">No categories found</div>';
        return;
    }
    container.innerHTML = `<div class="divide-y divide-glass-border/20">${nodes.map(n => renderTreeNode(n, 0)).join('')}</div>`;
    attachTreeNodeListeners(container);
}

function renderTreeNode(node, depth) {
    const cp = node._checkpoint || {};
    const status = cp.status || 'unscraped';
    const itemCount = cp.item_count || 0;
    const gdrivePct = cp.gdrive_pct || 0;
    const lastScraped = cp.last_scraped
        ? new Date(cp.last_scraped).toLocaleDateString()
        : 'Never';

    const statusDot = {
        complete: 'bg-emerald-400',
        partial:  'bg-amber-400',
        unscraped: 'bg-gray-600',
    }[status] || 'bg-gray-600';

    const statusLabel = {
        complete:  '<span class="text-emerald-400">Complete</span>',
        partial:   '<span class="text-amber-400">Partial</span>',
        unscraped: '<span class="text-gray-500">Unscraped</span>',
    }[status] || '';

    const indent = depth * 16;
    const hasChildren = node.children && node.children.length > 0;
    const slug = node.slug || '';
    const name = node.name || slug;

    const childrenHtml = hasChildren
        ? node.children.map(c => renderTreeNode(c, depth + 1)).join('')
        : '';

    return `
        <div class="scraper-node" data-slug="${slug}" data-depth="${depth}">
            <div class="flex items-center gap-3 px-4 py-2.5 hover:bg-white/3 transition-colors"
                 style="padding-left: ${16 + indent}px">
                <!-- Expand/Collapse toggle -->
                <button class="tree-toggle w-4 h-4 flex-shrink-0 flex items-center justify-center text-text-muted hover:text-white transition-colors"
                    data-slug="${slug}" style="${hasChildren ? '' : 'visibility:hidden'}">
                    <span class="material-symbols-outlined text-[14px] tree-chevron-${slug}">${hasChildren ? 'chevron_right' : 'remove'}</span>
                </button>

                <!-- Status dot -->
                <div class="w-2 h-2 rounded-full flex-shrink-0 ${statusDot}"></div>

                <!-- Name -->
                <span class="text-sm text-white flex-1 truncate" title="${name}">${name}</span>

                <!-- Stats -->
                <div class="flex items-center gap-4 text-[10px] font-mono text-text-muted flex-shrink-0">
                    <span title="Items scraped">${itemCount.toLocaleString()} items</span>
                    <span title="GDrive coverage" class="${gdrivePct > 80 ? 'text-emerald-400' : gdrivePct > 40 ? 'text-amber-400' : 'text-gray-500'}">${gdrivePct}% DL</span>
                    <span title="Last scraped">${lastScraped}</span>
                    ${statusLabel}
                </div>

                <!-- Action buttons -->
                <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                    ${status !== 'complete' ? `
                    <button class="tree-action-scrape px-2 py-1 bg-primary/10 border border-primary/20 text-primary text-[10px] rounded hover:bg-primary/20 transition-all"
                        data-slug="${slug}" title="Scrape this category">
                        <span class="material-symbols-outlined text-[12px]">play_arrow</span>
                    </button>` : ''}
                    ${status === 'partial' ? `
                    <button class="tree-action-resume px-2 py-1 bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[10px] rounded hover:bg-blue-500/20 transition-all"
                        data-slug="${slug}" title="Resume scraping">
                        <span class="material-symbols-outlined text-[12px]">replay</span>
                    </button>` : ''}
                    <button class="tree-action-force px-2 py-1 bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px] rounded hover:bg-amber-500/20 transition-all"
                        data-slug="${slug}" title="Force rescrape (preserves enrichment data)">
                        <span class="material-symbols-outlined text-[12px]">refresh</span>
                    </button>
                </div>
            </div>

            <!-- Children (initially collapsed) -->
            ${hasChildren ? `
            <div class="tree-children-${slug} hidden">
                ${childrenHtml}
            </div>` : ''}
        </div>
    `;
}

function attachTreeNodeListeners(container) {
    // Toggle expand/collapse
    container.querySelectorAll('.tree-toggle').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const slug = btn.dataset.slug;
            const childrenEl = container.querySelector(`.tree-children-${slug}`);
            const chevron = container.querySelector(`.tree-chevron-${slug}`);
            if (childrenEl) {
                childrenEl.classList.toggle('hidden');
                if (chevron) chevron.textContent = childrenEl.classList.contains('hidden') ? 'chevron_right' : 'expand_more';
            }
        });
    });

    // Scrape action
    container.querySelectorAll('.tree-action-scrape').forEach(btn => {
        btn.addEventListener('click', async () => {
            const slug = btn.dataset.slug;
            if (!confirm(`Scrape category: ${slug}?`)) return;
            await triggerScrape(slug, []);
        });
    });

    // Resume action
    container.querySelectorAll('.tree-action-resume').forEach(btn => {
        btn.addEventListener('click', async () => {
            const slug = btn.dataset.slug;
            await triggerScrape(slug, ['--resume']);
        });
    });

    // Force rescrape
    container.querySelectorAll('.tree-action-force').forEach(btn => {
        btn.addEventListener('click', async () => {
            const slug = btn.dataset.slug;
            if (!confirm(`Force rescrape "${slug}"?\n\nThis will UPDATE existing items with fresh data from the website.\nTags, colors, embeddings, favorites, and collections are PRESERVED.`)) return;
            await triggerScrape(slug, ['--force']);
        });
    });
}

async function triggerScrape(slug, extraArgs) {
    try {
        showToast(`Starting scrape: ${slug}...`);
        const res = await apiPost('/api/tasks/start', {
            type: 'scrape',
            args: ['--category', slug, ...extraArgs],
        });
        if (res.success) {
            showToast(`Scrape started for: ${slug}`, 'success');
        } else {
            showToast('Failed to start: ' + (res.error || 'unknown'), 'error');
        }
    } catch (e) {
        showToast('Error starting scrape task', 'error');
        console.error(e);
    }
}

function initScraperTreeButtons(deps) {
    document.getElementById('scraper-tree-refresh')?.addEventListener('click', () => {
        scraperTreeLoaded = false; // force reload
        const container = document.getElementById('scraper-tree-container');
        if (container) {
            container.innerHTML = '<div class="p-8 text-center text-text-muted text-sm">Refreshing...</div>';
            scraperTreeLoaded = true;
            loadScraperTree();
        }
    });

    document.getElementById('scraper-bulk-unscraped')?.addEventListener('click', async () => {
        if (!confirm('Scrape all unscraped categories? This may take a long time.')) return;
        try {
            const tree = await apiGet('/api/scraper/categories');
            const unscraped = flattenTree(tree).filter(n => n._checkpoint?.status === 'unscraped');
            if (unscraped.length === 0) { showToast('No unscraped categories found'); return; }
            showToast(`Queueing ${unscraped.length} categories...`);
            for (const node of unscraped.slice(0, 5)) { // safety: start max 5
                await triggerScrape(node.slug, []);
                await new Promise(r => setTimeout(r, 500));
            }
        } catch (e) { showToast('Bulk scrape failed', 'error'); }
    });

    document.getElementById('scraper-bulk-resume')?.addEventListener('click', async () => {
        if (!confirm('Resume all partial category scrapes?')) return;
        try {
            const tree = await apiGet('/api/scraper/categories');
            const partial = flattenTree(tree).filter(n => n._checkpoint?.status === 'partial');
            if (partial.length === 0) { showToast('No partial categories found'); return; }
            for (const node of partial.slice(0, 5)) {
                await triggerScrape(node.slug, ['--resume']);
                await new Promise(r => setTimeout(r, 500));
            }
        } catch (e) { showToast('Bulk resume failed', 'error'); }
    });
}

function flattenTree(nodes) {
    const result = [];
    for (const n of (nodes || [])) {
        result.push(n);
        if (n.children) result.push(...flattenTree(n.children));
    }
    return result;
}


// ═══════════════════════════════════════════════════════════════
// DATA QUALITY TAB — 2.3
// ═══════════════════════════════════════════════════════════════

async function loadQualityData() {
    await Promise.all([
        loadTagHealth(),
        loadNearDuplicates(),
        loadMissingData(),
    ]);
}

async function loadTagHealth() {
    try {
        const data = await apiGet('/api/quality/tag-health');

        // Counts
        const totalEl = document.getElementById('quality-total-tags');
        const orphanEl = document.getElementById('quality-orphan-count');
        if (totalEl) totalEl.textContent = (data.total_tags || 0).toLocaleString();
        if (orphanEl) orphanEl.textContent = (data.orphan_count || 0).toLocaleString();

        // Top tags
        const topEl = document.getElementById('quality-top-tags');
        if (topEl && data.top_tags?.length) {
            const max = data.top_tags[0]?.count || 1;
            topEl.innerHTML = data.top_tags.map(t => {
                const pct = Math.round(t.count / max * 100);
                return `<div class="flex items-center gap-2 text-xs">
                    <span class="w-28 truncate text-text-muted" title="${t.name}">${t.name}</span>
                    <div class="flex-1 bg-white/5 rounded-full h-1.5 overflow-hidden">
                        <div class="h-full bg-primary/70 rounded-full" style="width:${pct}%"></div>
                    </div>
                    <span class="text-text-muted w-8 text-right font-mono">${t.count}</span>
                </div>`;
            }).join('');
        }

        // Bottom tags
        const bottomEl = document.getElementById('quality-bottom-tags');
        if (bottomEl && data.bottom_tags?.length) {
            bottomEl.innerHTML = data.bottom_tags.map(t => `
                <div class="flex items-center gap-2 text-xs">
                    <span class="flex-1 text-text-muted truncate" title="${t.name}">${t.name}</span>
                    <span class="text-[10px] font-mono bg-white/5 px-1.5 py-0.5 rounded text-text-muted">${t.count}×</span>
                </div>`).join('');
        }

        // Orphan list
        const orphanList = document.getElementById('quality-orphan-list');
        if (orphanList && data.orphan_tags?.length) {
            orphanList.innerHTML = data.orphan_tags.map(t =>
                `<span class="text-[10px] font-mono px-2 py-0.5 bg-white/5 border border-glass-border rounded text-text-muted">${t.name}</span>`
            ).join('');
        } else if (orphanList) {
            orphanList.innerHTML = '<div class="text-xs text-emerald-400">No orphan tags found ✓</div>';
        }
    } catch (e) {
        console.error('Tag health load failed', e);
    }
}

async function loadNearDuplicates() {
    try {
        const dupes = await apiGet('/api/quality/near-duplicate-tags');
        const countEl = document.getElementById('quality-dupe-count');
        if (countEl) countEl.textContent = dupes.length.toLocaleString();

        if (dupes.length > 0) {
            const section = document.getElementById('quality-dupes-section');
            const list = document.getElementById('quality-dupes-list');
            if (section) section.classList.remove('hidden');
            if (list) {
                list.innerHTML = dupes.slice(0, 50).map(d => `
                    <div class="flex items-center gap-3 text-xs py-1">
                        <span class="text-text-muted font-mono w-32 truncate">${d.normalized}</span>
                        <div class="flex gap-1 flex-wrap flex-1">
                            ${d.variants.map(v =>
                                `<span class="px-2 py-0.5 bg-amber-500/10 border border-amber-500/20 text-amber-400 rounded text-[10px] font-mono">${v.name}</span>`
                            ).join('')}
                        </div>
                        <span class="text-[10px] text-text-muted">${d.count} variants</span>
                    </div>`).join('');
            }
        }
    } catch (e) { console.error('Near dup load failed', e); }
}

async function loadMissingData() {
    const container = document.getElementById('quality-missing-data');
    if (!container) return;
    try {
        const rows = await apiGet('/api/quality/missing-data');
        if (!rows || rows.length === 0) {
            container.innerHTML = '<div class="p-8 text-center text-emerald-400 text-xs">No missing data found ✓</div>';
            return;
        }
        container.innerHTML = rows.map(r => {
            const barStyles = [
                { pct: r.no_image_pct, color: 'bg-blue-400/50' },
                { pct: r.no_gdrive_pct, color: 'bg-emerald-400/50' },
                { pct: r.no_tags_pct, color: 'bg-pink-400/50' },
                { pct: r.no_embeddings_pct, color: 'bg-purple-400/50' },
            ];

            const renderBar = ({ pct, color }) =>
                `<div class="text-right">
                    <div class="text-[10px] font-mono ${pct > 50 ? 'text-red-400' : pct > 20 ? 'text-amber-400' : 'text-text-muted'}">${pct}%</div>
                    <div class="h-1 bg-white/5 rounded-full mt-0.5 overflow-hidden">
                        <div class="h-full ${color} rounded-full" style="width:${pct}%"></div>
                    </div>
                </div>`;

            // Make row clickable — jumps to gallery with category filter
            const galleryUrl = `/?category=${encodeURIComponent(r.slug)}`;

            return `<div class="grid grid-cols-[1fr_60px_80px_80px_80px_80px] gap-0 items-center px-4 py-2.5 hover:bg-white/3 transition-colors cursor-pointer group"
                    onclick="window.location.href='${galleryUrl}'" title="Browse ${r.name} in gallery">
                <span class="text-xs text-white group-hover:text-primary transition-colors truncate" title="${r.name}">${r.name}</span>
                <span class="text-right text-[10px] font-mono text-text-muted">${r.total.toLocaleString()}</span>
                ${renderBar({ pct: r.no_image_pct, color: 'bg-blue-400/50' })}
                ${renderBar({ pct: r.no_gdrive_pct, color: 'bg-emerald-400/50' })}
                ${renderBar({ pct: r.no_tags_pct, color: 'bg-pink-400/50' })}
                ${renderBar({ pct: r.no_embeddings_pct, color: 'bg-purple-400/50' })}
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<div class="p-8 text-center text-red-400 text-xs">Failed to load data</div>';
        console.error('Missing data load failed', e);
    }
}

function initQualityButtons() {
    // Refresh button
    document.getElementById('quality-refresh-btn')?.addEventListener('click', () => {
        document.getElementById('quality-top-tags').innerHTML = '<div class="text-xs text-text-muted">Loading...</div>';
        document.getElementById('quality-missing-data').innerHTML = '<div class="p-8 text-center text-text-muted text-xs italic">Loading...</div>';
        loadQualityData();
    });

    // Delete orphan tags
    document.getElementById('quality-delete-orphans-btn')?.addEventListener('click', async () => {
        const countEl = document.getElementById('quality-orphan-count');
        const count = parseInt(countEl?.textContent) || 0;
        if (count === 0) { showToast('No orphan tags to delete'); return; }
        if (!confirm(`Delete ${count} orphan tags with no items attached?\nThis cannot be undone.`)) return;
        try {
            const res = await apiPost('/api/quality/delete-orphan-tags', {});
            showToast(`Deleted ${res.deleted} orphan tags`, 'success');
            // Reload tag health
            await loadTagHealth();
        } catch (e) {
            showToast('Delete failed', 'error');
            console.error(e);
        }
    });
}
