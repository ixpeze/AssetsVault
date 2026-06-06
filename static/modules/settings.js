import { apiGet, apiPost } from './api.js';
import { showToast } from './toast.js';

export async function loadSettings() {
    const dirInput = document.getElementById('setting-download-dir');
    const quotaInput = document.getElementById('setting-disk-quota');
    const collisionInput = document.getElementById('setting-collision-mode');
    const concurrencyInput = document.getElementById('setting-concurrency');
    const retryInput = document.getElementById('setting-retry-count');
    
    if (!dirInput || !quotaInput) return;

    try {
        const settings = await apiGet('/api/settings');
        dirInput.value = settings.download_directory || '';
        quotaInput.value = settings.disk_quota || '50.0';
        if (collisionInput) collisionInput.value = settings.collision_mode || 'auto_rename';
        if (concurrencyInput) concurrencyInput.value = settings.concurrency || '2';
        if (retryInput) retryInput.value = settings.retry_count || '3';
    } catch (e) {
        showToast('Failed to load settings', 'error');
        console.error(e);
    }
}

export async function chooseDownloadDirectory() {
    const dirInput = document.getElementById('setting-download-dir');
    if (!dirInput) return;

    const promptForServerPath = (message) => {
        const current = dirInput.value || 'data/downloads';
        const manual = window.prompt(
            `${message}\n\nEnter a folder path on the server PC, or a UNC network share path such as \\\\OTHER-PC\\Assets\\Downloads:`,
            current
        );
        if (manual && manual.trim()) {
            dirInput.value = manual.trim();
            showToast('Download path set. Click Save Settings to apply it.', 'info');
        }
    };

    try {
        const res = await apiPost('/api/settings/choose-download-directory', {});
        if (res.download_directory) {
            dirInput.value = res.download_directory;
            showToast('Download folder selected', 'success');
        } else if (res.cancelled) {
            showToast('Folder selection cancelled');
        } else {
            promptForServerPath(res.error || 'Folder picker is not available in this browser session.');
        }
    } catch (e) {
        promptForServerPath('Folder picker is not available in this browser session.');
        console.error(e);
    }
}

export async function saveSettings() {
    const dirInput = document.getElementById('setting-download-dir');
    const quotaInput = document.getElementById('setting-disk-quota');
    const collisionInput = document.getElementById('setting-collision-mode');
    const concurrencyInput = document.getElementById('setting-concurrency');
    const retryInput = document.getElementById('setting-retry-count');

    if (!dirInput || !quotaInput) return;

    const data = {
        download_directory: dirInput.value.trim(),
        disk_quota: quotaInput.value.trim()
    };

    if (collisionInput) data.collision_mode = collisionInput.value;
    if (concurrencyInput) data.concurrency = concurrencyInput.value.trim();
    if (retryInput) data.retry_count = retryInput.value.trim();

    try {
        const res = await apiPost('/api/settings', data);
        if (res.error) {
            showToast(res.error, 'error');
        } else {
            showToast('Settings saved successfully', 'success');
            await loadSettings();
        }
    } catch (e) {
        showToast('Failed to save settings', 'error');
        console.error(e);
    }
}
