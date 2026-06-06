import { apiGet, apiPost } from './api.js';
import { showToast } from './toast.js';
import { state } from './state.js';

let _activeInterval = null;
let _clientAgentInterval = null;
let _previousActive = new Map(); // Track previous state to detect transitions
let _previousClientJobs = new Map();
let _downloadStatusBar = null;   // Persistent status bar element
const CLIENT_AGENT_URLS = ['http://127.0.0.1:56789', 'http://localhost:56789'];
let _clientAgentUrl = CLIENT_AGENT_URLS[0];
let _installerPromptVisible = false;
const INSTALLER_DISMISS_KEY = 'obsidian_client_agent_prompt_dismissed_until';

function _isServerLocalClient() {
    const host = window.location.hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '::1';
}

function _downloadUrlForItem(itemId, fallbackUrl = '') {
    if (fallbackUrl) return fallbackUrl;
    const item = state.items.find(i => Number(i.id) === Number(itemId));
    return item?.gdrive_link || item?.mirror_link || '';
}

function _itemForDownload(itemId) {
    return state.items.find(i => Number(i.id) === Number(itemId)) || {};
}

function _escapeAttr(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/`/g, '&#96;');
}

export async function enqueueDownload(itemId, downloadUrl = '') {
    if (!itemId) return;

    const targetUrl = _downloadUrlForItem(itemId, downloadUrl);
    if (!targetUrl) {
        showToast('No download link available for this item', 'error');
        return;
    }

    try {
        const item = _itemForDownload(itemId);
        const res = await _postClientAgent('/download', {
            item_id: itemId,
            title: item.title || `Item ${itemId}`,
            category_slug: item.category_slug || '',
            url: targetUrl,
        });
        if (res.error) {
            throw new Error(res.error);
        }
        showToast(res.message || 'Download queued on this PC', 'success');
        _startClientAgentMonitor();
        return;
    } catch (e) {
        console.info('[Downloader] Client agent unavailable:', e);
        _offerClientAgentInstaller({ fallbackUrl: targetUrl, force: true });
        showToast('Client downloader is not running on this PC', 'error');
    }
}

export async function checkClientDownloaderBootstrap() {
    if (_isInstallerPromptDismissed()) return false;

    try {
        const health = await _probeClientAgent();
        if (health?.ok) {
            _clearInstallerPromptDismissal();
            return true;
        }
    } catch {
        _offerClientAgentInstaller();
        return false;
    }
    _offerClientAgentInstaller();
    return false;
}

async function _getClientAgent(path) {
    const errors = [];
    for (const baseUrl of [_clientAgentUrl, ...CLIENT_AGENT_URLS.filter(url => url !== _clientAgentUrl)]) {
        try {
            const data = await _fetchClientAgent(baseUrl, path);
            _clientAgentUrl = baseUrl;
            return data;
        } catch (error) {
            errors.push(error);
        }
    }
    throw errors[0] || new Error('Client agent unavailable');
}

async function _probeClientAgent() {
    return _getClientAgent('/health');
}

async function _fetchClientAgent(baseUrl, path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1200);
    try {
        const resp = await fetch(`${baseUrl}${path}`, { signal: controller.signal });
        return await resp.json();
    } finally {
        clearTimeout(timeout);
    }
}

async function _postClientAgent(path, body) {
    const errors = [];
    for (const baseUrl of [_clientAgentUrl, ...CLIENT_AGENT_URLS.filter(url => url !== _clientAgentUrl)]) {
        try {
            const data = await _postClientAgentTo(baseUrl, path, body);
            _clientAgentUrl = baseUrl;
            return data;
        } catch (error) {
            errors.push(error);
        }
    }
    throw errors[0] || new Error('Client agent unavailable');
}

async function _postClientAgentTo(baseUrl, path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1200);
    try {
        const resp = await fetch(`${baseUrl}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: controller.signal,
        });
        return await resp.json();
    } finally {
        clearTimeout(timeout);
    }
}

function _startClientAgentMonitor() {
    if (_clientAgentInterval) return;

    _clientAgentInterval = setInterval(async () => {
        try {
            const jobs = await _getClientAgent('/jobs');
            const active = jobs
                .filter(job => job.status === 'queued' || job.status === 'downloading')
                .map(job => ({
                    item_id: Number(job.item_id) || 0,
                    job_id: job.id,
                    title: job.title,
                    progress: job.progress || 0,
                    bytes_written: job.bytes_written || 0,
                    total_bytes: job.total_bytes || 0,
                    speed_kbps: job.speed_kbps || 0,
                    status: job.status,
                }));

            for (const job of jobs) {
                const previous = _previousClientJobs.get(job.id);
                if (previous && previous.status !== job.status && job.status === 'completed') {
                    showToast(`Download complete: ${_truncateTitle(job.title || 'Asset', 40)}`, 'success');
                } else if (previous && previous.status !== job.status && job.status === 'failed') {
                    showToast(`Download failed: ${_truncateTitle(job.title || 'Asset', 40)}`, 'error');
                }
            }
            _previousClientJobs = new Map(jobs.map(job => [job.id, { ...job }]));

            _updateStatusBar(active);
            if (active.length === 0) {
                _stopClientAgentMonitor();
            }
        } catch (e) {
            _stopClientAgentMonitor();
        }
    }, 1500);
}

function _stopClientAgentMonitor() {
    if (_clientAgentInterval) {
        clearInterval(_clientAgentInterval);
        _clientAgentInterval = null;
    }
    _hideStatusBar();
}

function _isInstallerPromptDismissed() {
    try {
        return Date.now() < Number(localStorage.getItem(INSTALLER_DISMISS_KEY) || 0);
    } catch {
        return false;
    }
}

function _dismissInstallerPrompt() {
    try {
        localStorage.setItem(INSTALLER_DISMISS_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));
    } catch {
        // Ignore storage failures; the close button should still work.
    }
}

function _clearInstallerPromptDismissal() {
    try {
        localStorage.removeItem(INSTALLER_DISMISS_KEY);
    } catch {
        // Ignore storage failures.
    }
}

function _offerClientAgentInstaller({ fallbackUrl = '', force = false } = {}) {
    if (_installerPromptVisible) return;
    if (!force && _isInstallerPromptDismissed()) return;
    _installerPromptVisible = true;

    const downloadUrl = '/install-client-downloader.bat';
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm px-4';
    modal.innerHTML = `
        <div class="w-full max-w-md rounded-lg border border-glass-border bg-[#111118] shadow-2xl p-5 text-white">
            <div class="flex items-start gap-3">
                <span class="material-symbols-outlined text-primary text-[24px]">download</span>
                <div class="min-w-0">
                    <div class="flex items-start justify-between gap-3">
                        <h3 class="text-sm font-semibold font-display">Client downloader required</h3>
                        <button id="client-agent-close" class="shrink-0 w-7 h-7 rounded border border-glass-border bg-white/5 text-text-muted hover:text-white hover:bg-white/10" title="Close">
                            <span class="material-symbols-outlined text-[15px]">close</span>
                        </button>
                    </div>
                    <p class="mt-2 text-xs leading-5 text-text-muted">
                        To save assets directly on this PC without filling the server, run the installer once.
                        If it is already installed, make sure the local agent is running on port 56789.
                    </p>
                </div>
            </div>
            <div class="mt-4 flex flex-wrap justify-end gap-2">
                ${fallbackUrl ? '<button id="client-agent-fallback" class="h-9 px-3 rounded border border-glass-border bg-white/5 text-xs text-text-muted hover:text-white hover:bg-white/10">Open source link once</button>' : ''}
                <button id="client-agent-retry" class="h-9 px-3 rounded border border-glass-border bg-white/5 text-xs text-text-muted hover:text-white hover:bg-white/10">Check again</button>
                <button id="client-agent-dismiss" class="h-9 px-3 rounded border border-glass-border bg-white/5 text-xs text-text-muted hover:text-white hover:bg-white/10">Don\'t remind for 7 days</button>
                <a id="client-agent-download" href="${downloadUrl}" download class="h-9 px-3 rounded border border-primary/40 bg-primary/20 text-xs font-semibold text-primary hover:text-white hover:bg-primary/30 inline-flex items-center gap-1.5">
                    <span class="material-symbols-outlined text-[15px]">download</span>
                    Download installer
                </a>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const closeModal = () => {
        modal.remove();
        _installerPromptVisible = false;
    };
    modal.querySelector('#client-agent-close')?.addEventListener('click', closeModal);
    modal.querySelector('#client-agent-dismiss')?.addEventListener('click', () => {
        _dismissInstallerPrompt();
        closeModal();
    });
    modal.querySelector('#client-agent-retry')?.addEventListener('click', async () => {
        try {
            const health = await _probeClientAgent();
            if (health?.ok) {
                _clearInstallerPromptDismissal();
                showToast('Client downloader detected', 'success');
                closeModal();
                return;
            }
        } catch {
            // Show the same concise status message below.
        }
        showToast('Client downloader still not reachable', 'error');
    });
    modal.querySelector('#client-agent-fallback')?.addEventListener('click', () => {
        window.open(fallbackUrl, '_blank', 'noopener');
        closeModal();
    });
}

export async function pauseDownload(jobId) {
    if (!jobId) return;
    try {
        showToast('Pausing download...');
        const res = await apiPost('/api/downloads/pause', { job_id: jobId });
        if (res.error) {
            showToast(res.error, 'error');
        } else {
            showToast(res.message || 'Download paused', 'success');
            loadDownloads();
        }
    } catch (e) {
        showToast('Failed to pause download', 'error');
        console.error(e);
    }
}

export async function resumeDownload(jobId) {
    if (!jobId) return;
    try {
        showToast('Resuming download...');
        const res = await apiPost('/api/downloads/resume', { job_id: jobId });
        if (res.error) {
            showToast(res.error, 'error');
        } else {
            showToast(res.message || 'Download resumed', 'success');
            loadDownloads();
            startActiveDownloadsMonitor();
        }
    } catch (e) {
        showToast('Failed to resume download', 'error');
        console.error(e);
    }
}

export async function openDownloadsFolder() {
    try {
        const res = await apiPost('/api/downloads/open-folder', {});
        if (res.error) {
            showToast(`${res.error} Path: ${res.path || 'data/downloads'}`, 'error');
        } else {
            showToast(res.message || 'Downloads folder opened', 'success');
        }
    } catch (e) {
        showToast('Failed to open downloads folder', 'error');
        console.error(e);
    }
}

export async function revealDownloadedItem(itemId) {
    if (!itemId) return;
    try {
        const res = await apiPost('/api/downloads/reveal-item', { item_id: itemId });
        if (res.error) {
            if (res.download_url) {
                window.open(res.download_url, '_blank', 'noopener');
                showToast('Opening downloaded archive in browser', 'info');
            } else {
                showToast(res.error, 'error');
            }
        } else {
            showToast(res.message || 'Downloaded archive revealed', 'success');
        }
    } catch (e) {
        showToast('Failed to open downloaded archive', 'error');
        console.error(e);
    }
}

export async function loadDownloads() {
    const listBody = document.getElementById('downloads-list-body');
    if (!listBody) return;

    try {
        const jobs = await apiGet('/api/downloads/jobs');
        const active = await apiGet('/api/downloads/active');
        const activeMap = new Map(active.map(a => [a.job_id, a]));

        if (jobs.length === 0 && active.length === 0) {
            listBody.innerHTML = `
                <tr>
                    <td colspan="7" class="p-8 text-center text-text-muted text-xs italic">
                        No downloads queued yet.
                    </td>
                </tr>
            `;
            return;
        }

        listBody.innerHTML = jobs.map(job => {
            const activeJob = activeMap.get(job.id);
            const status = activeJob ? 'downloading' : job.status;
            const progress = activeJob ? activeJob.progress : job.progress;
            const speed = activeJob ? `${activeJob.speed_kbps} KB/s` : '-';
            const bytesWritten = activeJob ? activeJob.bytes_written : job.bytes_written;
            const totalBytes = activeJob ? activeJob.total_bytes : job.total_bytes;
            
            const progressStr = progress >= 0 ? `${progress}%` : '-';
            const sizeStr = totalBytes > 0 ? _formatBytes(bytesWritten) + ' / ' + _formatBytes(totalBytes) : '-';
            
            // Format status badge
            let badgeClass = 'bg-gray-500/10 text-gray-400 border-gray-500/20';
            if (status === 'downloading') badgeClass = 'bg-primary/10 text-primary border-primary/20 animate-pulse';
            else if (status === 'completed') badgeClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
            else if (status === 'failed') badgeClass = 'bg-red-500/10 text-red-400 border-red-500/20';
            else if (status === 'paused') badgeClass = 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
            else if (status === 'pending') badgeClass = 'bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse';

            // Format date
            const date = job.created_at ? new Date(job.created_at).toLocaleString() : '-';

            // Actions markup
            let actionBtn = '<span class="text-text-muted text-[10px] font-mono">-</span>';
            if (status === 'downloading' || status === 'pending') {
                actionBtn = `
                    <button class="pause-btn px-2 py-0.5 bg-yellow-500/10 hover:bg-yellow-500/20 border border-yellow-500/20 text-yellow-400 hover:text-white rounded text-[10px] font-bold uppercase transition-all" data-id="${job.id}">
                        Pause
                    </button>
                `;
            } else if (status === 'paused') {
                actionBtn = `
                    <button class="resume-btn px-2 py-0.5 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-emerald-400 hover:text-white rounded text-[10px] font-bold uppercase transition-all" data-id="${job.id}">
                        Resume
                    </button>
                `;
            }

            return `
                <tr class="border-b border-glass-border/10 hover:bg-white/2 transition-colors">
                    <td class="px-4 py-3 text-xs text-white font-medium truncate max-w-[250px]" title="${job.title}">
                        ${job.title}
                    </td>
                    <td class="px-4 py-3 text-[10px] font-mono text-text-muted">
                        ${job.id}
                    </td>
                    <td class="px-4 py-3 text-xs">
                        <span class="px-2 py-0.5 border rounded text-[10px] font-medium ${badgeClass}">
                            ${status.toUpperCase()}
                        </span>
                    </td>
                    <td class="px-4 py-3 text-xs text-text-muted font-mono">
                        <div class="flex items-center gap-2">
                            <span class="w-8">${progressStr}</span>
                            <div class="w-16 bg-white/5 rounded-full h-1.5 overflow-hidden">
                                <div class="h-full rounded-full transition-all duration-300 ${status === 'downloading' ? 'bg-primary' : status === 'completed' ? 'bg-emerald-400' : 'bg-gray-500'}" style="width: ${progress}%"></div>
                            </div>
                        </div>
                    </td>
                    <td class="px-4 py-3 text-xs text-text-muted font-mono">
                        ${speed}
                    </td>
                    <td class="px-4 py-3 text-[10px] text-text-muted font-mono" title="${sizeStr}">
                        ${date}
                    </td>
                    <td class="px-4 py-3 text-right">
                        ${actionBtn}
                    </td>
                </tr>
            `;
        }).join('');

        // Wire event delegation if not already wired
        if (!listBody.dataset.wired) {
            listBody.dataset.wired = 'true';
            listBody.addEventListener('click', (e) => {
                const pauseBtn = e.target.closest('.pause-btn');
                const resumeBtn = e.target.closest('.resume-btn');
                if (pauseBtn) {
                    pauseDownload(parseInt(pauseBtn.dataset.id));
                } else if (resumeBtn) {
                    resumeDownload(parseInt(resumeBtn.dataset.id));
                }
            });
        }

    } catch (e) {
        listBody.innerHTML = `
            <tr>
                <td colspan="7" class="p-8 text-center text-red-400 text-xs font-medium">
                    Failed to load downloads list
                </td>
            </tr>
        `;
        console.error('Downloads list load failed', e);
    }
}

export function startActiveDownloadsMonitor() {
    // Gallery downloads are now client-local only. Keep the legacy server queue
    // visible in the dashboard, but do not let host queue state alter cards.
    return;

    if (_activeInterval) return;

    _activeInterval = setInterval(async () => {
        const active = await apiGet('/api/downloads/active').catch(() => []);
        
        // Update activeDownloads Map in global state
        state.activeDownloads.clear();
        for (const a of active) {
            state.activeDownloads.set(a.item_id, a);

            const newStatus = a.status === 'pending' ? 'queued' : 'downloading';
            _setCardButtonState(a.item_id, newStatus);
        }

        // Detect completed downloads (was active before, now gone)
        _detectCompletions(active);

        // Update persistent status bar
        _updateStatusBar(active);

        // Update gallery card overlays with real-time progress
        updateGalleryDownloadIndicators(active);

        // If the downloads tab is open, reload the list
        const downloadsPanel = document.getElementById('dash-panel-downloads');
        if (downloadsPanel && !downloadsPanel.classList.contains('hidden')) {
            loadDownloads();
        }

        // Stop polling if there are no active downloads
        const hasActiveJobs = active.some(a => a.status === 'downloading' || a.status === 'pending');
        if (active.length === 0 && !hasActiveJobs) {
            // One final check for recently completed items
            _refreshCompletedCards();
            _hideStatusBar();
            stopActiveDownloadsMonitor();
        }
    }, 1000);
}

export function stopActiveDownloadsMonitor() {
    if (_activeInterval) {
        clearInterval(_activeInterval);
        _activeInterval = null;
    }
}

// ── Real-time Gallery Card Overlay ──

function updateGalleryDownloadIndicators(activeList) {
    const activeIds = new Set(activeList.map(a => a.item_id));
    
    // Scan all visible cards
    document.querySelectorAll('.gallery-card').forEach(card => {
        const id = parseInt(card.dataset.id);
        const overlay = card.querySelector('.download-overlay');
        if (!overlay) return;

        if (activeIds.has(id)) {
            const activeJob = activeList.find(a => a.item_id === id);
            const speed = activeJob.speed_kbps > 1024 
                ? `${(activeJob.speed_kbps / 1024).toFixed(1)} MB/s` 
                : `${activeJob.speed_kbps} KB/s`;
            const totalStr = activeJob.total_bytes > 0 ? _formatBytes(activeJob.total_bytes) : '';

            overlay.classList.remove('hidden');
            if (activeJob.status === 'pending') {
                overlay.innerHTML = `
                    <div class="flex flex-col items-center gap-1 bg-black/70 backdrop-blur-sm px-3 py-2 rounded-lg border border-primary/30">
                        <div class="flex items-center gap-1.5 text-primary text-[11px] font-medium">
                            <span class="material-symbols-outlined text-[14px] animate-pulse">hourglass_top</span>
                            <span>Queued</span>
                        </div>
                    </div>
                `;
            } else {
                overlay.innerHTML = `
                    <div class="flex flex-col items-center gap-1 bg-black/70 backdrop-blur-sm px-3 py-2 rounded-lg border border-primary/30">
                        <div class="flex items-center gap-1.5 text-primary text-[11px] font-medium">
                            <span class="material-symbols-outlined text-[14px] animate-spin">progress_activity</span>
                            <span>${activeJob.progress}%</span>
                            <span class="text-text-muted text-[9px]">${speed}</span>
                        </div>
                        <div class="w-full bg-white/10 rounded-full h-1 overflow-hidden" style="min-width: 80px">
                            <div class="h-full bg-primary rounded-full transition-all duration-300" style="width: ${activeJob.progress}%"></div>
                        </div>
                        ${totalStr ? `<span class="text-text-muted text-[8px] font-mono">${_formatBytes(activeJob.bytes_written)} / ${totalStr}</span>` : ''}
                    </div>
                `;
            }
        } else {
            overlay.classList.add('hidden');
            overlay.innerHTML = '';
        }
    });
}

// ── Completion Detection & Card Update ──

function _detectCompletions(currentActive) {
    const currentIds = new Set(currentActive.map(a => a.item_id));

    // Check items that were previously active but are no longer
    for (const [itemId, prevData] of _previousActive.entries()) {
        if (!currentIds.has(itemId)) {
            // This item is no longer active — check if it completed
            _checkAndUpdateCompletedItem(itemId);
        }
    }

    // Update the previous state map
    _previousActive.clear();
    for (const a of currentActive) {
        _previousActive.set(a.item_id, { ...a });
    }
}

async function _checkAndUpdateCompletedItem(itemId) {
    try {
        // Fetch item status from API to confirm it's 'local'
        const res = await apiGet(`/api/items/${itemId}`);
        if (res && res.status === 'local') {
            showToast(`Download complete: ${_truncateTitle(res.title || `Item #${itemId}`, 40)}`, 'success');
            _setCardButtonState(itemId, 'local');
        } else {
            // Download was paused, cancelled, or failed
            _setCardButtonState(itemId, 'online');
            
            // Check if there was a failure to show toast
            const jobs = await apiGet('/api/downloads/jobs');
            const job = jobs.find(j => j.item_id === itemId);
            if (job && job.status === 'failed') {
                showToast(`Download failed: ${_truncateTitle((res && res.title) || `Item #${itemId}`, 40)}`, 'error');
            }
        }
    } catch (e) {
        console.error('[Downloader] Failed to check completed item:', e);
    }
}

function _updateItemStatus(itemId, status) {
    const item = state.items?.find(i => Number(i.id) === Number(itemId));
    if (item) {
        item.status = status;
    }
}

function _setCardButtonState(itemId, status) {
    // 1. Update in-memory state so virtualization keeps the button correct
    _updateItemStatus(itemId, status);

    const card = document.querySelector(`.gallery-card[data-id="${itemId}"]`);
    if (!card) return;

    const btnContainer = card.querySelector('.download-btn, .download-queued-btn');
    if (!btnContainer) return;
    if (btnContainer.dataset.downloadState === status) return;

    if (status === 'queued') {
        // Replace with animated queued icon
        btnContainer.outerHTML = `<button class="download-queued-btn flex items-center justify-center w-7 h-7 rounded border border-primary/30 bg-primary/10 text-primary cursor-wait animate-pulse transition-all" data-download-state="queued" title="Queued for download"><span class="material-symbols-outlined text-[16px]">hourglass_top</span></button>`;
    } else if (status === 'downloading') {
        btnContainer.outerHTML = `<button class="download-queued-btn flex items-center justify-center w-7 h-7 rounded border border-primary/30 bg-primary/10 text-primary cursor-wait animate-pulse transition-all" data-download-state="downloading" title="Downloading"><span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span></button>`;
    } else {
        // Reset to download button
        const targetUrl = _downloadUrlForItem(itemId, btnContainer.dataset.downloadUrl || '');
        const title = 'Download with client app';
        btnContainer.outerHTML = `<button class="download-btn flex items-center justify-center w-7 h-7 rounded border border-glass-border hover:bg-frost-hover text-text-muted hover:text-white transition-all" data-id="${itemId}" data-download-url="${_escapeAttr(targetUrl)}" data-download-state="online" title="${title}"><span class="material-symbols-outlined text-[16px]">download_for_offline</span></button>`;
    }
}

async function _refreshCompletedCards() {
    // When monitor stops, refresh all cards that might have completed
    try {
        const jobs = await apiGet('/api/downloads/jobs');
        for (const job of jobs) {
            if (job.status === 'completed' && job.local_file_path) {
                _setCardButtonState(job.item_id, 'local');
            }
        }
    } catch (e) {
        console.error('[Downloader] Failed to refresh completed cards:', e);
    }
}

// ── Persistent Download Status Bar ──

function _updateStatusBar(activeList) {
    const downloading = activeList.filter(a => a.status === 'downloading' || a.status === 'queued');
    if (downloading.length === 0) return;

    if (!_downloadStatusBar) {
        _downloadStatusBar = document.createElement('div');
        _downloadStatusBar.id = 'download-status-bar';
        _downloadStatusBar.className = 'fixed bottom-0 left-0 right-0 z-[55] bg-[#0a0a0f]/95 backdrop-blur-md border-t border-primary/20 px-4 py-2 transition-all duration-300';
        document.body.appendChild(_downloadStatusBar);
        // Push body content up
        document.body.style.paddingBottom = '48px';
    }

    const totalProgress = downloading.reduce((sum, d) => sum + (d.progress || 0), 0) / downloading.length;
    const totalSpeed = downloading.reduce((sum, d) => sum + d.speed_kbps, 0);
    const totalBytes = downloading.reduce((sum, d) => sum + d.bytes_written, 0);
    const totalSize = downloading.reduce((sum, d) => sum + d.total_bytes, 0);

    const speedStr = totalSpeed > 1024 
        ? `${(totalSpeed / 1024).toFixed(1)} MB/s` 
        : `${totalSpeed} KB/s`;

    _downloadStatusBar.innerHTML = `
        <div class="flex items-center gap-4 max-w-screen-xl mx-auto">
            <div class="flex items-center gap-2 text-primary">
                <span class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
                <span class="text-xs font-medium">${downloading.length} local download${downloading.length > 1 ? 's' : ''}</span>
            </div>
            <div class="flex-1 bg-white/5 rounded-full h-1.5 overflow-hidden">
                <div class="h-full bg-gradient-to-r from-primary to-emerald-400 rounded-full transition-all duration-300" style="width: ${totalProgress}%"></div>
            </div>
            <div class="flex items-center gap-3 text-[11px] font-mono text-text-muted shrink-0">
                <span>${Math.round(totalProgress)}%</span>
                <span class="text-primary/60">|</span>
                <span>${speedStr}</span>
                ${totalSize > 0 ? `<span class="text-primary/60">|</span><span>${_formatBytes(totalBytes)} / ${_formatBytes(totalSize)}</span>` : ''}
            </div>
        </div>
    `;
}

function _hideStatusBar() {
    if (_downloadStatusBar) {
        _downloadStatusBar.style.opacity = '0';
        _downloadStatusBar.style.transform = 'translateY(100%)';
        setTimeout(() => {
            _downloadStatusBar?.remove();
            _downloadStatusBar = null;
            document.body.style.paddingBottom = '';
        }, 300);
    }
}

// ── Utilities ──

function _formatBytes(bytes) {
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

function _truncateTitle(title, maxLen) {
    if (!title) return '';
    return title.length > maxLen ? title.slice(0, maxLen) + '...' : title;
}
