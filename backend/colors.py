
# ============================================================================
# Color Definitions (48 Semantic Buckets: 12 Hues x 4 Variants)
# ============================================================================

COLOR_FAMILIES = [
    # ROW 1: LIGHT / PASTEL (L 70-98, S 10-100)
    {"name": "red_light",    "hex": "#fca5a5", "sql": "(h>=345 OR h<15) AND s>10 AND l>=75"},
    {"name": "orange_light", "hex": "#fdba74", "sql": "h BETWEEN 15 AND 45 AND s>10 AND l>=75"},
    {"name": "yellow_light", "hex": "#fde047", "sql": "h BETWEEN 45 AND 75 AND s>10 AND l>=75"},
    {"name": "lime_light",   "hex": "#bef264", "sql": "h BETWEEN 75 AND 105 AND s>10 AND l>=75"},
    {"name": "green_light",  "hex": "#86efac", "sql": "h BETWEEN 105 AND 150 AND s>10 AND l>=75"},
    {"name": "teal_light",   "hex": "#5eead4", "sql": "h BETWEEN 150 AND 180 AND s>10 AND l>=75"},
    {"name": "cyan_light",   "hex": "#67e8f9", "sql": "h BETWEEN 180 AND 200 AND s>10 AND l>=75"},
    {"name": "sky_light",    "hex": "#7dd3fc", "sql": "h BETWEEN 200 AND 220 AND s>10 AND l>=75"},
    {"name": "blue_light",   "hex": "#93c5fd", "sql": "h BETWEEN 220 AND 260 AND s>10 AND l>=75"},
    {"name": "indigo_light", "hex": "#a5b4fc", "sql": "h BETWEEN 260 AND 290 AND s>10 AND l>=75"},
    {"name": "purple_light", "hex": "#d8b4fe", "sql": "h BETWEEN 290 AND 315 AND s>10 AND l>=75"},
    {"name": "pink_light",   "hex": "#f9a8d4", "sql": "h BETWEEN 315 AND 345 AND s>10 AND l>=75"},

    # ROW 2: VIVID / BRIGHT (L 40-75, S 50-100)
    {"name": "red",          "hex": "#ef4444", "sql": "(h>=345 OR h<15) AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "orange",       "hex": "#f97316", "sql": "h BETWEEN 15 AND 45 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "yellow",       "hex": "#eab308", "sql": "h BETWEEN 45 AND 75 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "lime",         "hex": "#84cc16", "sql": "h BETWEEN 75 AND 105 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "green",        "hex": "#22c55e", "sql": "h BETWEEN 105 AND 150 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "teal",         "hex": "#14b8a6", "sql": "h BETWEEN 150 AND 180 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "cyan",         "hex": "#06b6d4", "sql": "h BETWEEN 180 AND 200 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "sky",          "hex": "#0ea5e9", "sql": "h BETWEEN 200 AND 220 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "blue",         "hex": "#3b82f6", "sql": "h BETWEEN 220 AND 260 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "indigo",       "hex": "#6366f1", "sql": "h BETWEEN 260 AND 290 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "purple",       "hex": "#a855f7", "sql": "h BETWEEN 290 AND 315 AND s>=50 AND l BETWEEN 40 AND 75"},
    {"name": "pink",         "hex": "#ec4899", "sql": "h BETWEEN 315 AND 345 AND s>=50 AND l BETWEEN 40 AND 75"},

    # ROW 3: DARK / DEEP (L 0-40, Any S)
    {"name": "red_dark",     "hex": "#991b1b", "sql": "(h>=345 OR h<15) AND l BETWEEN 15 AND 40"},
    {"name": "orange_dark",  "hex": "#9a3412", "sql": "h BETWEEN 15 AND 45 AND l BETWEEN 15 AND 40"},
    {"name": "yellow_dark",  "hex": "#854d0e", "sql": "h BETWEEN 45 AND 75 AND l BETWEEN 15 AND 40"},
    {"name": "lime_dark",    "hex": "#3f6212", "sql": "h BETWEEN 75 AND 105 AND l BETWEEN 15 AND 40"},
    {"name": "green_dark",   "hex": "#166534", "sql": "h BETWEEN 105 AND 150 AND l BETWEEN 15 AND 40"},
    {"name": "teal_dark",    "hex": "#115e59", "sql": "h BETWEEN 150 AND 180 AND l BETWEEN 15 AND 40"},
    {"name": "cyan_dark",    "hex": "#155e75", "sql": "h BETWEEN 180 AND 200 AND l BETWEEN 15 AND 40"},
    {"name": "sky_dark",     "hex": "#075985", "sql": "h BETWEEN 200 AND 220 AND l BETWEEN 15 AND 40"},
    {"name": "blue_dark",    "hex": "#1e3a8a", "sql": "h BETWEEN 220 AND 260 AND l BETWEEN 15 AND 40"},
    {"name": "indigo_dark",  "hex": "#3730a3", "sql": "h BETWEEN 260 AND 290 AND l BETWEEN 15 AND 40"},
    {"name": "purple_dark",  "hex": "#581c87", "sql": "h BETWEEN 290 AND 315 AND l BETWEEN 15 AND 40"},
    {"name": "pink_dark",    "hex": "#831843", "sql": "h BETWEEN 315 AND 345 AND l BETWEEN 15 AND 40"},

    # ROW 4: NEUTRAL / MUTED
    {"name": "warm_gray",   "hex": "#d6d3d1", "sql": "(h>=345 OR h<45) AND s<=50 AND s>10 AND l BETWEEN 40 AND 75"},
    {"name": "beige",       "hex": "#e7e5e4", "sql": "(h>=345 OR h<45) AND s<=30 AND l>=75"},
    {"name": "white",       "hex": "#fafafa", "sql": "l >= 95"},
    {"name": "light_gray",  "hex": "#e4e4e7", "sql": "s <= 10 AND l BETWEEN 70 AND 95"},
    {"name": "gray",        "hex": "#a1a1aa", "sql": "s <= 10 AND l BETWEEN 40 AND 70"},
    {"name": "slate",       "hex": "#64748b", "sql": "h BETWEEN 200 AND 260 AND s BETWEEN 5 AND 40 AND l BETWEEN 40 AND 70"},
    {"name": "dark_gray",   "hex": "#52525b", "sql": "s <= 10 AND l BETWEEN 15 AND 40"},
    {"name": "black",       "hex": "#18181b", "sql": "l < 15"},
    {"name": "brown",       "hex": "#78350f", "sql": "h BETWEEN 15 AND 50 AND s>10 AND l BETWEEN 15 AND 35"},
    {"name": "olive",       "hex": "#5a6628", "sql": "h BETWEEN 50 AND 90 AND s<=50 AND s>10 AND l BETWEEN 30 AND 60"},
    {"name": "teal_muted",  "hex": "#3d6865", "sql": "h BETWEEN 150 AND 190 AND s<=40 AND s>10 AND l BETWEEN 30 AND 60"},
    {"name": "purple_muted","hex": "#6b5876", "sql": "h BETWEEN 260 AND 320 AND s<=40 AND s>10 AND l BETWEEN 30 AND 60"},
]
