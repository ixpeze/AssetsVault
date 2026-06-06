// ── Dashboard Module ──
import { state } from './state.js';
import { dom } from './dom.js';
import { apiGet, apiPost } from './api.js';
import { resetTabCache } from './dashboard-tabs.js';

export function showDashboard(deps) {
    const { updateDashboard, fetchAnalytics, loadDbHealth, loadCoverageHeatmap } = deps;
    state.activeView = "dashboard";
    dom.scrollContainer.classList.add("hidden");
    dom.dashboardView.classList.remove("hidden");
    dom.allAssetsLink.classList.remove("bg-frost-hover", "text-white");
    dom.favoritesLink.classList.remove("bg-frost-hover", "text-white");
    dom.dashboardLink.classList.add("bg-frost-hover", "text-white");
    updateDashboard();
    fetchAnalytics();
    loadDbHealth();
    loadCoverageHeatmap();
    if (state.dashboardInterval) clearInterval(state.dashboardInterval);
    state.dashboardInterval = setInterval(updateDashboard, 2000);
}

export function showGallery() {
    state.activeView = "gallery";
    dom.dashboardView.classList.add("hidden");
    dom.scrollContainer.classList.remove("hidden");
    dom.dashboardLink?.classList.remove("bg-frost-hover", "text-white");
    if (state.dashboardInterval) { clearInterval(state.dashboardInterval); state.dashboardInterval = null; }
    resetTabCache(); // Scraper + Quality tabs reload fresh next dashboard open
}


export async function updateDashboard(deps) {
    if (state.activeView !== "dashboard") return;
    const { renderDashStats, renderTaskTable, renderTaskLogs, updateTaskCardStatuses } = deps;
    try {
        const [stats, tasksData] = await Promise.all([apiGet("/api/stats"), apiGet("/api/tasks")]);
        renderDashStats(stats);
        renderTaskTable(tasksData);
        renderTaskLogs(tasksData);
        state.runningTasks.clear();
        Object.values(tasksData).forEach(task => { if (task.status === 'running') state.runningTasks.add(task.type); });
        updateTaskCardStatuses(tasksData);
        if (state.dashboardInterval) clearInterval(state.dashboardInterval);
        const interval = state.runningTasks.size > 0 ? 2000 : 10000;
        state.dashboardInterval = setInterval(() => updateDashboard(deps), interval);
    } catch (e) { console.error("Dashboard update failed", e); }
}

export function renderDashStats(stats) {
    if (!dom.dashStats) return;
    const coverage = stats.coverage || {};
    const colorsPct = coverage.colors_percent || 0;
    const embedsPct = coverage.embeddings_percent || 0;
    const tagsPct = coverage.tags_percent || 0;
    const enrichedPct = coverage.enriched_percent || 0;
    dom.dashStats.innerHTML = `
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Total Assets</div><div class="text-2xl font-display font-bold text-white">${stats.total_items || 0}</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">With Images</div><div class="text-2xl font-display font-bold text-white">${stats.total_with_images || 0}</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">With GDrive</div><div class="text-2xl font-display font-bold text-white">${stats.total_with_gdrive || 0}</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Categories</div><div class="text-2xl font-display font-bold text-white">${stats.total_categories || 0}</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Fully Enriched</div><div class="text-2xl font-display font-bold text-cyan-400">${stats.total_fully_enriched || 0}</div><div class="text-xs text-text-muted mt-1">${enrichedPct.toFixed(1)}% of all items</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Tagged</div><div class="text-2xl font-display font-bold text-white">${stats.total_tags || 0}</div><div class="text-xs text-text-muted mt-1">${tagsPct.toFixed(1)}%</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Colors</div><div class="text-2xl font-display font-bold text-white">${stats.total_colors || 0}</div><div class="text-xs text-text-muted mt-1">${colorsPct.toFixed(1)}%</div></div>
        <div class="bg-[#151515] border border-glass-border rounded-xl p-4"><div class="text-text-muted text-xs uppercase font-bold tracking-wider mb-1">Embeddings</div><div class="text-2xl font-display font-bold text-white">${stats.total_embeddings || 0}</div><div class="text-xs text-text-muted mt-1">${embedsPct.toFixed(1)}%</div></div>
    `;
}

export async function fetchAnalytics() {
    try { renderAnalytics(await apiGet("/api/analytics")); } catch (e) { console.error("Failed to fetch analytics", e); }
}

export function renderAnalytics(data) {
    const tagsEl = document.getElementById("analytics-tags");
    if (tagsEl && data.top_tags && data.top_tags.length > 0) {
        const maxCount = data.top_tags[0].count;
        tagsEl.innerHTML = data.top_tags.slice(0, 15).map(tag => {
            const pct = Math.round((tag.count / maxCount) * 100);
            return `<div class="flex items-center gap-2 text-xs"><span class="w-24 truncate text-text-muted">${tag.name}</span><div class="flex-1 bg-white/5 rounded-full h-2 overflow-hidden"><div class="h-full bg-primary/60 rounded-full" style="width:${pct}%"></div></div><span class="text-text-muted w-8 text-right">${tag.count}</span></div>`;
        }).join("");
    } else if (tagsEl) { tagsEl.innerHTML = '<div class="text-xs text-text-muted italic">No tags found. Run the AI Tagger first.</div>'; }

    const catsEl = document.getElementById("analytics-categories");
    if (catsEl && data.category_distribution && data.category_distribution.length > 0) {
        const maxCat = data.category_distribution[0].count;
        catsEl.innerHTML = data.category_distribution.slice(0, 12).map(cat => {
            const pct = Math.round((cat.count / maxCat) * 100);
            const label = cat.slug.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
            return `<div class="flex items-center gap-2 text-xs"><span class="w-28 truncate text-text-muted" title="${cat.slug}">${label}</span><div class="flex-1 bg-white/5 rounded-full h-2 overflow-hidden"><div class="h-full bg-secondary/60 rounded-full" style="width:${pct}%"></div></div><span class="text-text-muted w-8 text-right">${cat.count}</span></div>`;
        }).join("");
    }

    const coverEl = document.getElementById("analytics-coverage");
    if (coverEl && data.coverage) {
        const c = data.coverage;
        const total = c.total || 1;
        const metrics = [
            { label: "Fully Enriched", value: c.fully_enriched, color: "#22d3ee" },
            { label: "Images", value: c.images, color: "#60a5fa" },
            { label: "GDrive Links", value: c.gdrive, color: "#34d399" },
            { label: "Tags", value: c.tags, color: "#f472b6" },
            { label: "Colors", value: c.colors, color: "#fb923c" },
            { label: "Embeddings", value: c.embeddings, color: "#c084fc" },
        ];
        coverEl.innerHTML = metrics.map(m => {
            const pct = Math.round((m.value / total) * 100);
            return `<div><div class="flex justify-between text-xs mb-1"><span class="text-text-muted">${m.label}</span><span class="text-white font-mono">${m.value.toLocaleString()} / ${total.toLocaleString()} (${pct}%)</span></div><div class="bg-white/5 rounded-full h-2.5 overflow-hidden"><div class="h-full rounded-full transition-all duration-500" style="width:${pct}%; background-color:${m.color}99"></div></div></div>`;
        }).join("");
    }
}

export async function loadDbHealth() {
    try {
        const h = await apiGet('/api/analytics/db-health');
        const size = document.getElementById('dbh-size');
        const fts = document.getElementById('dbh-fts');
        const embed = document.getElementById('dbh-embed');
        const orphan = document.getElementById('dbh-orphan');
        if (size) size.textContent = `${h.db_size_mb} MB`;
        if (fts) { fts.textContent = h.fts_synced ? '✓ Synced' : `⚠ Off by ${Math.abs(h.items_total - h.fts_count)}`; fts.className = `text-sm font-mono ${h.fts_synced ? 'text-green-400' : 'text-amber-400'}`; }
        if (embed) embed.textContent = `${h.embedded_pct}%`;
        if (orphan) { orphan.textContent = h.orphan_embeddings; orphan.className = `text-lg font-mono ${h.orphan_embeddings > 0 ? 'text-amber-400' : 'text-green-400'}`; }
    } catch (e) { console.error('DB health fetch failed', e); }
}

export async function loadCoverageHeatmap() {
    const container = document.getElementById('coverage-heatmap');
    if (!container) return;
    try {
        const rows = await apiGet('/api/analytics/coverage');
        if (!rows || !rows.length) { container.innerHTML = '<div class="text-xs text-text-muted italic">No data</div>'; return; }
        container.innerHTML = rows.slice(0, 15).map(r => {
            const tagPct = r.total > 0 ? Math.round(r.tagged / r.total * 100) : 0;
            const gdrivePct = r.total > 0 ? Math.round(r.has_gdrive / r.total * 100) : 0;
            const embedPct = r.total > 0 ? Math.round(r.has_embedding / r.total * 100) : 0;
            return `<div class="flex items-center gap-3 text-xs"><span class="w-28 truncate text-text-muted" title="${r.name}">${r.name}</span><span class="text-[10px] text-text-muted w-10 text-right">${r.total}</span><div class="flex-1 flex flex-col gap-0.5"><div class="flex items-center gap-1"><div class="h-1.5 bg-primary/80 rounded-sm transition-all" style="width:${tagPct}%" title="Tagged: ${tagPct}%"></div><span class="text-[9px] text-text-muted">${tagPct}%</span></div><div class="flex items-center gap-1"><div class="h-1.5 bg-emerald-500/80 rounded-sm" style="width:${gdrivePct}%" title="GDrive: ${gdrivePct}%"></div><span class="text-[9px] text-text-muted">${gdrivePct}%</span></div><div class="flex items-center gap-1"><div class="h-1.5 bg-purple-400/80 rounded-sm" style="width:${embedPct}%" title="Embedded: ${embedPct}%"></div><span class="text-[9px] text-text-muted">${embedPct}%</span></div></div></div>`;
        }).join('');
    } catch (e) { container.innerHTML = '<div class="text-xs text-red-500">Failed to load</div>'; }
}

export function renderTaskTable(tasks) {
    if (!dom.taskListBody) return;
    const list = Object.values(tasks).sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    if (list.length === 0) { dom.taskListBody.innerHTML = '<tr><td colspan="4" class="px-4 py-8 text-center italic">No active tasks</td></tr>'; return; }
    dom.taskListBody.innerHTML = list.map(t => {
        const isRunning = t.status === "running";
        const statusColor = isRunning ? "text-green-400" : (t.status === "failed" ? "text-red-400" : "text-text-muted");
        const progress = t.progress ? `${t.progress}%` : (isRunning ? "Running..." : "Done");
        return `<tr class="border-t border-glass-border/50">
            <td class="px-4 py-3 font-medium text-white">${t.type}</td>
            <td class="px-4 py-3 ${statusColor} text-xs font-mono uppercase">${t.status}</td>
            <td class="px-4 py-3 text-xs font-mono">${progress}</td>
            <td class="px-4 py-3 text-right">${isRunning ? `<button onclick="window.stopTask('${t.id}')" class="text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20 px-2 py-1 rounded transition-colors">Stop</button>` : ''}</td>
        </tr>`;
    }).join("");
}

export function renderTaskLogs(tasks) {
    if (!dom.taskTerminal) return;
    const taskArray = Object.values(tasks).sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
    const tabsContainer = document.getElementById("log-task-tabs");
    if (tabsContainer && taskArray.length > 0) {
        tabsContainer.innerHTML = taskArray.map(t => {
            const isActive = state.selectedTaskId === t.id;
            const statusColor = t.status === 'running' ? 'bg-green-400' : t.status === 'failed' ? 'bg-red-400' : 'bg-gray-400';
            const activeClass = isActive ? 'bg-primary/20 border-primary text-primary' : 'bg-white/5 border-glass-border text-text-muted hover:bg-white/10';
            return `<button onclick="window.selectTaskLog('${t.id}')" class="flex items-center gap-2 px-3 py-1.5 rounded-lg border ${activeClass} text-xs font-semibold transition-colors whitespace-nowrap">
                <div class="w-2 h-2 rounded-full ${statusColor}"></div>
                <span>${t.type}</span>
                ${t.progress > 0 ? `<span class="text-[10px] opacity-60">${t.progress}%</span>` : ''}
            </button>`;
        }).join('');
        if (!state.selectedTaskId && taskArray.length > 0) state.selectedTaskId = taskArray[0].id;
    }
    let selectedTask = taskArray.find(t => t.id === state.selectedTaskId);
    if (!selectedTask && taskArray.length > 0) { selectedTask = taskArray[0]; state.selectedTaskId = selectedTask.id; }
    if (!selectedTask || !selectedTask.logs || selectedTask.logs.length === 0) {
        dom.taskTerminal.innerHTML = '<div class="text-text-muted opacity-50">No logs available</div>'; return;
    }
    const formattedLogs = selectedTask.logs.map((line, i) => {
        const lineNum = `<span class="text-text-muted opacity-40 select-none">${String(i + 1).padStart(4, ' ')} | </span>`;
        return lineNum + colorizeLogLine(line);
    }).join('\n');
    const isAtBottom = dom.taskTerminal.scrollHeight - dom.taskTerminal.clientHeight <= dom.taskTerminal.scrollTop + 50;
    dom.taskTerminal.innerHTML = formattedLogs;
    if (isAtBottom) dom.taskTerminal.scrollTop = dom.taskTerminal.scrollHeight;
}

export function selectTaskLog(taskId, updateDashboardFn) {
    state.selectedTaskId = taskId;
    if (updateDashboardFn) updateDashboardFn();
}

function colorizeLogLine(line) {
    if (/ERROR|ERR\b|Failed|Traceback|Exception/.test(line)) return `<span class="text-red-400">${line}</span>`;
    if (/WARNING|⚠/.test(line)) return `<span class="text-yellow-400">${line}</span>`;
    if (line.match(/^\[(\d+)\/(\d+)\]/)) return `<span class="text-cyan-400 font-bold">${line}</span>`;
    if (/\[(tags|colors|embed|cat)\]\s+✓|→\s+Done/.test(line)) return `<span class="text-green-400">${line}</span>`;
    if (/\[(tags|colors|embed|cat)\]\s+(kept|skip|—)/.test(line)) return `<span class="text-gray-500">${line}</span>`;
    if (/^[=─]{10,}|Pipeline Complete|Enrichment Coverage/.test(line)) return `<span class="text-blue-300 font-bold">${line}</span>`;
    if (/^\s+(Total|With|Fully|Tags|Colors|Embeddings|Items|Skipped|Failed)/.test(line)) return `<span class="text-blue-200">${line}</span>`;
    if (/Missing:/.test(line)) return `<span class="text-gray-400 italic">${line}</span>`;
    return `<span class="text-gray-300">${line}</span>`;
}

export function updateTaskCardStatuses(tasks) {
    const taskMapping = { 'scrape': 'scraper', 'pipeline': 'pipeline', 'recapture': 'recapture' };
    for (const prefix of Object.keys(taskMapping)) {
        const idBase = taskMapping[prefix];
        const statusEl = document.getElementById(`${idBase}-status`);
        const startBtn = document.getElementById(`start-${idBase}`);
        const stopBtn = document.getElementById(`stop-${idBase}`);
        const resumeBtn = document.getElementById(`start-${idBase}-resume`);
        const forceBtn = document.getElementById(`start-${idBase}-force`);
        const lastRunEl = document.getElementById(`${idBase}-last-run`);
        if (statusEl) statusEl.innerHTML = `<div class="w-2 h-2 rounded-full bg-gray-500"></div><span class="text-[10px] text-text-muted">Idle</span>`;
        if (startBtn) startBtn.classList.remove('hidden');
        if (resumeBtn) resumeBtn.classList.remove('hidden');
        if (forceBtn) forceBtn.classList.remove('hidden');
        if (stopBtn) stopBtn.classList.add('hidden');
        const recentTask = Object.values(tasks).filter(t => t.type === prefix).sort((a, b) => new Date(b.start_time) - new Date(a.start_time))[0];
        if (recentTask && lastRunEl) lastRunEl.textContent = new Date(recentTask.start_time).toLocaleString();
    }
    for (const [id, t] of Object.entries(tasks)) {
        if (t.status === 'running') {
            const prefix = id.split('_')[0];
            const idBase = taskMapping[prefix];
            if (!idBase) continue;
            const statusEl = document.getElementById(`${idBase}-status`);
            const startBtn = document.getElementById(`start-${idBase}`);
            const stopBtn = document.getElementById(`stop-${idBase}`);
            const resumeBtn = document.getElementById(`start-${idBase}-resume`);
            const forceBtn = document.getElementById(`start-${idBase}-force`);
            if (statusEl) statusEl.innerHTML = `<div class="w-2 h-2 rounded-full bg-green-400 pulse-dot"></div><span class="text-[10px] text-green-400">Running</span>`;
            if (startBtn) startBtn.classList.add('hidden');
            if (resumeBtn) resumeBtn.classList.add('hidden');
            if (forceBtn) forceBtn.classList.add('hidden');
            if (stopBtn) stopBtn.classList.remove('hidden');
        }
    }
}

export async function startTask(type, args, showToast, updateDashboardFn) {
    try {
        showToast(`Starting ${type}...`);
        const res = await apiPost("/api/tasks/start", { type, args });
        if (res.success) { if (updateDashboardFn) updateDashboardFn(); }
        else showToast("Failed to start: " + res.error);
    } catch (e) { showToast("Error starting task"); console.error(e); }
}

export async function stopTask(taskId, showToast, updateDashboardFn) {
    try {
        await apiPost("/api/tasks/stop", { task_id: taskId });
        showToast("Task stopped");
        if (updateDashboardFn) updateDashboardFn();
    } catch (e) { console.error(e); }
}

export async function stopTaskByType(taskType, showToast, updateDashboardFn) {
    const tasksData = await apiGet("/api/tasks");
    const runningTask = Object.values(tasksData).find(t => t.type === taskType && t.status === 'running');
    if (runningTask) await stopTask(runningTask.id, showToast, updateDashboardFn);
    else showToast(`No running ${taskType} task found`);
}

export async function clearCompletedTasks(showToast, updateDashboardFn) {
    const tasksData = await apiGet("/api/tasks");
    const toClear = Object.values(tasksData).filter(t => t.status !== 'running');
    if (toClear.length === 0) { showToast("No completed tasks to clear", "info"); return; }
    if (!confirm(`Clear ${toClear.length} completed/stopped task(s) from view?`)) return;
    for (const task of toClear) await apiPost("/api/tasks/stop", { task_id: task.id });
    if (state.selectedTaskId && !tasksData[state.selectedTaskId]) state.selectedTaskId = null;
    showToast(`Cleared ${toClear.length} task(s)`, "success");
    if (updateDashboardFn) updateDashboardFn();
}

export async function startPipeline(args, showToast, updateDashboardFn) {
    try {
        await apiPost("/api/tasks/pipeline", { args });
        showToast("Enrichment pipeline started (Tags + Colors + Embeddings)");
        if (updateDashboardFn) updateDashboardFn();
    } catch (e) { console.error("Pipeline start failed", e); showToast("Failed to start pipeline"); }
}

export function startPipelineWithPrompt(showToast, updateDashboardFn) {
    const limit = prompt("How many items to process? (leave blank for all):");
    const args = [];
    if (limit && !isNaN(limit) && parseInt(limit) > 0) args.push("--limit", limit);
    startPipeline(args, showToast, updateDashboardFn);
}

export async function startRecapture(args, showToast, updateDashboardFn) {
    try {
        await apiPost("/api/tasks/recapture", { args });
        showToast("Link recapture started");
        if (updateDashboardFn) updateDashboardFn();
    } catch (e) { console.error("Recapture start failed", e); showToast("Failed to start recapture task"); }
}

export function startRecaptureWithPrompt(showToast, updateDashboardFn) {
    const limit = prompt("How many missing links to check? (leave blank for all):");
    const args = [];
    if (limit && !isNaN(limit) && parseInt(limit) > 0) args.push("--limit", limit);
    startRecapture(args, showToast, updateDashboardFn);
}
