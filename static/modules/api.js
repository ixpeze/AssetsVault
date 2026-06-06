// ── API Fetch Wrappers ──

// ── Client-side TTL cache for rarely-changing endpoints ──
const _cache = new Map();
const _CACHE_TTL = {
    '/api/colors': 60_000,      // 60s
    '/api/categories': 60_000,  // 60s
    '/api/tags/cloud': 60_000,  // 60s
    '/api/stats': 15_000,       // 15s
    '/api/counts': 15_000,      // 15s
    '/api/taxonomy': 60_000,    // 60s
};

function _getAdminToken() {
    try {
        return localStorage.getItem('obsidian_admin_token') || '';
    } catch {
        return '';
    }
}

function _setAdminToken(token) {
    try {
        localStorage.setItem('obsidian_admin_token', token);
    } catch {
        // Browser storage may be unavailable in hardened/private contexts.
    }
    document.cookie = `admin_token=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
}

function _authHeaders(extra = {}) {
    const token = _getAdminToken();
    return token ? { ...extra, "Authorization": `Bearer ${token}` } : extra;
}

async function _maybeRetryWithAdminToken(resp, retryFn) {
    if (resp.status !== 401) return resp;

    let data = null;
    try {
        data = await resp.clone().json();
    } catch {
        // Non-JSON 401 responses should fall through to the caller.
    }

    if (data?.error !== 'admin authorization required') return resp;

    const token = window.prompt('Admin token required for this action:');
    if (!token) return resp;

    _setAdminToken(token.trim());
    return retryFn();
}

function _getCachedTTL(endpoint) {
    for (const [prefix, ttl] of Object.entries(_CACHE_TTL)) {
        if (endpoint === prefix || endpoint.startsWith(prefix + '?')) return ttl;
    }
    return 0;
}

export async function apiGet(endpoint) {
    // Check in-memory cache first
    const ttl = _getCachedTTL(endpoint);
    if (ttl > 0) {
        const cached = _cache.get(endpoint);
        if (cached && (Date.now() - cached.ts) < ttl) {
            return cached.data;
        }
    }

    let resp = await fetch(endpoint, { headers: _authHeaders() });
    resp = await _maybeRetryWithAdminToken(resp, () => fetch(endpoint, { headers: _authHeaders() }));
    if (!resp.ok) throw new Error(`API error: ${resp.status}`);
    const data = await resp.json();

    // Store in cache if endpoint is cacheable
    if (ttl > 0) {
        _cache.set(endpoint, { data, ts: Date.now() });
    }

    return data;
}

/** Invalidate all cached API responses (call after mutations). */
export function invalidateApiCache() {
    _cache.clear();
}

export async function apiPost(endpoint, body) {
    const request = () => fetch(endpoint, {
        method: "POST",
        headers: _authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
    });
    let resp = await request();
    resp = await _maybeRetryWithAdminToken(resp, request);
    // Invalidate read cache after mutations
    invalidateApiCache();
    return resp.json();
}

export async function apiDelete(endpoint) {
    const request = () => fetch(endpoint, { method: "DELETE", headers: _authHeaders() });
    let resp = await request();
    resp = await _maybeRetryWithAdminToken(resp, request);
    invalidateApiCache();
    return resp.json();
}
