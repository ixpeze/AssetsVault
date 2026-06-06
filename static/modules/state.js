// ── Shared Application State ──
// Single source of truth — imported by all other modules.

export const state = {
    items: [],
    categories: [],
    categoryTree: [],
    collections: [],
    tags: [],
    taxonomyTree: [],
    stats: {},
    currentPage: 1,
    totalPages: 1,
    total: 0,
    perPage: 24,
    searchQuery: "",
    activeCategory: "",
    activeTaxonomy: "",
    activeTier: "",
    activeTag: "",
    activeColor: "",
    semanticSearch: false,
    activeCollection: null,
    sortBy: "newest",
    advancedFilters: {
        hasGdrive: "",
        hasImage: "",
        tier: ""
    },
    expandedCategories: new Set(),
    lightboxIndex: -1,
    loading: false,
    loadingMore: false,
    allLoaded: false,
    // Favorites & Multi-Select
    favoriteIds: new Set(),
    selectedIds: new Set(),
    showFavorites: false,
    showUntagged: false,
    smartCollections: [],
    // Context menu
    contextItemId: null,
    // Focus mode (U13)
    focusMode: localStorage.getItem('focusMode') === '1',
    // Tag cloud density (T9)
    tagDensity: parseInt(localStorage.getItem('tagDensity') || '30'),
    // Dashboard
    activeView: "gallery", // 'gallery' | 'dashboard'
    dashboardInterval: null,
    runningTasks: new Set(),
    selectedTaskId: null,
    // Tag AND/OR mode
    tagMode: localStorage.getItem('tagMode') || 'AND',
    activeDownloads: new Map(), // item_id -> activeJobData
};

// Tag Manager local state (kept alongside main state for cohesion)
export const tagManagerState = {
    allTags: [],
    filteredTags: [],
    selectedTagIds: new Set()
};
