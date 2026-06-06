"""
Build a smart virtual taxonomy from the flat 3DSkyFree categories.

Creates a hierarchical structure (~15 top-level groups) and maps every
original category to the correct taxonomy node.  Original categories
stay untouched – the taxonomy is a separate overlay.

Usage:
    python build_taxonomy.py --dry-run       # preview without touching DB
    python build_taxonomy.py --apply         # create tables and insert
    python build_taxonomy.py --apply --reset # drop & rebuild taxonomy
"""

import sqlite3, json, re, argparse, sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "3dskyfree.db"
PREVIEW_FILE = Path(__file__).parent / "taxonomy_preview.json"

# ── Taxonomy Tree Structure (Recursive, up to 4 levels) ─────────────────────
TAXONOMY_TREE = [
    # ─── FURNITURE (Level 1) ───
    {
        "slug": "furniture", "name": "Furniture", "icon": "chair",
        "children": [
            {
                "slug": "furniture-seating", "name": "Seating",
                "children": [
                    {"slug": "furniture-seating-sofa", "name": "Sofas"},
                    {"slug": "furniture-seating-armchair", "name": "Armchairs"},
                    {"slug": "furniture-seating-chair", "name": "Chairs"},
                    {"slug": "furniture-seating-stool", "name": "Stools & Benches"},
                    {"slug": "furniture-seating-other", "name": "Other Seating"},
                ]
            },
            {
                "slug": "furniture-tables", "name": "Tables",
                "children": [
                    {"slug": "furniture-tables-dining", "name": "Dining Tables"},
                    {"slug": "furniture-tables-coffee", "name": "Coffee & Side Tables"},
                    {"slug": "furniture-tables-desk", "name": "Desks & Consoles"},
                    {"slug": "furniture-tables-other", "name": "Other Tables"},
                ]
            },
            {
                "slug": "furniture-storage", "name": "Storage",
                "children": [
                    {"slug": "furniture-storage-wardrobe", "name": "Wardrobes"},
                    {"slug": "furniture-storage-cabinet", "name": "Cabinets & Sideboards"},
                    {"slug": "furniture-storage-shelving", "name": "Shelving & Racks"},
                    {"slug": "furniture-storage-other", "name": "Other Storage"},
                ]
            },
            {
                "slug": "furniture-beds", "name": "Beds",
                "children": [
                    {"slug": "furniture-beds-bed", "name": "Beds"},
                    {"slug": "furniture-beds-headboard", "name": "Headboards"},
                    {"slug": "furniture-beds-kids", "name": "Kids Beds & Cribs"},
                    {"slug": "furniture-beds-other", "name": "Other Bedroom Furniture"},
                ]
            },
            {
                "slug": "furniture-office", "name": "Office Furniture",
                "children": [
                    {"slug": "furniture-office-chair", "name": "Office Chairs"},
                    {"slug": "furniture-office-desk", "name": "Office Desks"},
                    {"slug": "furniture-office-other", "name": "Other Office"},
                ]
            },
            {"slug": "furniture-outdoor", "name": "Outdoor Furniture"},
            {"slug": "furniture-other", "name": "Other Furniture"},
        ]
    },

    # ─── LIGHTING ───
    {
        "slug": "lighting", "name": "Lighting", "icon": "lightbulb",
        "children": [
            {"slug": "lighting-ceiling", "name": "Ceiling Lights"},
            {"slug": "lighting-floor", "name": "Floor Lamps"},
            {"slug": "lighting-wall", "name": "Wall Lights"},
            {"slug": "lighting-table", "name": "Table Lamps"},
            {"slug": "lighting-decorative", "name": "Decorative"},
            {"slug": "lighting-outdoor", "name": "Outdoor Lighting"},
            {"slug": "lighting-other", "name": "Other Lighting"},
        ]
    },

    # ─── DECORATION ───
    {
        "slug": "decoration", "name": "Decoration", "icon": "palette",
        "children": [
            {
                "slug": "decoration-textiles", "name": "Textiles",
                "children": [
                    {"slug": "decoration-textiles-curtains", "name": "Curtains & Blinds"},
                    {"slug": "decoration-textiles-carpets", "name": "Carpets & Rugs"},
                    {"slug": "decoration-textiles-pillows", "name": "Pillows & Cushions"},
                    {"slug": "decoration-textiles-other", "name": "Other Textiles"},
                ]
            },
            {
                "slug": "decoration-wall", "name": "Wall Decor",
                "children": [
                    {"slug": "decoration-wall-art", "name": "Art & Frames"},
                    {"slug": "decoration-wall-mirror", "name": "Mirrors"},
                    {"slug": "decoration-wall-clock", "name": "Clocks"},
                    {"slug": "decoration-wall-other", "name": "Other Wall Decor"},
                ]
            },
            {
                "slug": "decoration-accessories", "name": "Accessories",
                "children": [
                    {"slug": "decoration-acc-vases", "name": "Vases & Pottery"},
                    {"slug": "decoration-acc-candles", "name": "Candles"},
                    {"slug": "decoration-acc-books", "name": "Books"},
                    {"slug": "decoration-acc-bathroom", "name": "Bathroom Sets"},
                    {"slug": "decoration-acc-other", "name": "Other Accessories"},
                ]
            },
            {"slug": "decoration-plants", "name": "Small Plants"},
            {"slug": "decoration-other", "name": "Other Decoration"},
        ]
    },

    # ─── MATERIALS (Dynamic Tags) ───
    {
        "slug": "materials", "name": "Materials", "icon": "texture",
        "children": [
            {"slug": "materials-wood", "name": "Wood", "dynamic_tag_source": "auto"},
            {"slug": "materials-fabric", "name": "Fabric", "dynamic_tag_source": "auto"},
            {"slug": "materials-stone", "name": "Stone & Marble", "dynamic_tag_source": "auto"},
            {"slug": "materials-tile", "name": "Tiles", "dynamic_tag_source": "auto"},
            {"slug": "materials-metal", "name": "Metal", "dynamic_tag_source": "auto"},
            {"slug": "materials-glass", "name": "Glass", "dynamic_tag_source": "auto"},
            {"slug": "materials-other", "name": "Other Materials"},
        ]
    },

    # ─── ROOMS & INTERIORS ───
    {
        "slug": "rooms", "name": "Rooms", "icon": "bed",
        "children": [
            {"slug": "rooms-living", "name": "Living Room"},
            {"slug": "rooms-bedroom", "name": "Bedroom"},
            {"slug": "rooms-kitchen", "name": "Kitchen"},
            {"slug": "rooms-bathroom", "name": "Bathroom"},
            {"slug": "rooms-kids", "name": "Kids Room"},
            {"slug": "rooms-office", "name": "Office"},
            {"slug": "rooms-dining", "name": "Dining Room"},
            {"slug": "rooms-other", "name": "Other Rooms"},
        ]
    },

    # ─── KITCHEN OBJECTS ───
    {
        "slug": "kitchen", "name": "Kitchen Objects", "icon": "kitchen",
        "children": [
            {"slug": "kitchen-appliances", "name": "Appliances"},
            {"slug": "kitchen-tableware", "name": "Tableware"},
            {"slug": "kitchen-food", "name": "Food"},
            {"slug": "kitchen-cookware", "name": "Cookware"},
            {"slug": "kitchen-other", "name": "Other Kitchen"},
        ]
    },

    # ─── ARCHITECTURE ───
    {
        "slug": "architecture", "name": "Architecture", "icon": "apartment",
        "children": [
            {"slug": "arch-doors", "name": "Doors"},
            {"slug": "arch-windows", "name": "Windows"},
            {"slug": "arch-stairs", "name": "Stairs"},
            {"slug": "arch-exterior", "name": "Exterior Elements"},
            {"slug": "arch-walls", "name": "Walls & Panels"},
            {"slug": "arch-columns", "name": "Columns"},
            {"slug": "arch-other", "name": "Other Architecture"},
        ]
    },

    # ─── TECHNOLOGY ───
    {
        "slug": "technology", "name": "Technology", "icon": "devices",
        "children": [
            {"slug": "tech-audio", "name": "Audio"},
            {"slug": "tech-tv", "name": "TV & Screens"},
            {"slug": "tech-computers", "name": "Computers"},
            {"slug": "tech-appliances", "name": "Home Appliances"},
            {"slug": "tech-other", "name": "Other Tech"},
        ]
    },

    # ─── NATURE ───
    {
        "slug": "nature", "name": "Nature", "icon": "forest",
        "children": [
            {"slug": "nature-trees", "name": "Trees"},
            {"slug": "nature-plants", "name": "Plants"},
            {"slug": "nature-flowers", "name": "Flowers"},
            {"slug": "nature-grass", "name": "Grass"},
            {"slug": "nature-landscape", "name": "Landscape"},
            {"slug": "nature-other", "name": "Other Nature"},
        ]
    },

    # ─── OTHER SECTIONS ───
    # ─── OTHER SECTIONS ───
    {
        "slug": "vehicles", "name": "Vehicles", "icon": "directions_car",
        "children": [
            {"slug": "vehicles-cars", "name": "Cars & Trucks"},
            {"slug": "vehicles-bikes", "name": "Bikes & Motorcycles"},
            {"slug": "vehicles-other", "name": "Other Vehicles"},
        ]
    },
    {
        "slug": "clothing", "name": "Clothing", "icon": "checkroom",
        "children": [
            {"slug": "clothing-shoes", "name": "Shoes"},
            {"slug": "clothing-bags", "name": "Bags & Luggage"},
            {"slug": "clothing-other", "name": "Other Clothing"},
        ]
    },
    {
        "slug": "characters", "name": "Characters", "icon": "pets",
        "children": [
            {"slug": "characters-people", "name": "People"},
            {"slug": "characters-animals", "name": "Animals"},
            {"slug": "characters-other", "name": "Other Characters"},
        ]
    },
    {
        "slug": "commercial", "name": "Commercial", "icon": "storefront",
        "children": [
            {"slug": "commercial-retail", "name": "Retail"},
            {"slug": "commercial-office", "name": "Office"},
            {"slug": "commercial-restaurant", "name": "Restaurant"},
            {"slug": "commercial-hotel", "name": "Hotel"},
            {"slug": "commercial-other", "name": "Other Commercial"},
        ]
    },
    {
        "slug": "scenes", "name": "Full Scenes", "icon": "view_in_ar",
        "children": [
            {"slug": "scenes-interior", "name": "Interior Scenes"},
            {"slug": "scenes-exterior", "name": "Exterior Scenes"},
            {"slug": "scenes-commercial", "name": "Commercial Scenes"},
            {"slug": "scenes-studio", "name": "Studio Setup"},
        ]
    },
    {"slug": "other", "name": "Other", "icon": "category", "children": [{"slug": "other-misc", "name": "Miscellaneous"}]},
]


# ── Keyword-based category → taxonomy mapping rules ──────────────────────
# Order matters: first match wins.  Patterns are case-insensitive.
# (regex_pattern, taxonomy_slug)
# ── Keyword-based category → taxonomy mapping rules ──────────────────────
# Order matters: first match wins.  Patterns are case-insensitive.
# (regex_pattern, taxonomy_slug)
KEYWORD_RULES = [
    # ─── DECOR HELPER prefix patterns ───
    (r"DECOR HELPER\s*-\s*CARPET",                    "decoration-textiles-carpets"),
    (r"DECOR HELPER\s*-\s*CURTAIN",                   "decoration-textiles-curtains"),
    (r"DECOR HELPER\s*-\s*PILLOW",                    "decoration-textiles-pillows"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*MOULDING",    "arch-columns"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*COLUMN",      "arch-columns"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*DECOR",       "decoration-other"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*DOOR",        "arch-doors"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*KITCHEN",     "kitchen-other"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*STAIR",       "arch-stairs"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*WALL",        "arch-walls"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*WINDOW",      "arch-windows"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*LIVINGROOM\s*-\s*SOFA", "furniture-seating-sofa"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*LIVINGROOM\s*-\s*ARMCHAIR", "furniture-seating-armchair"),
    (r"DECOR HELPER\s*-\s*CLASSIC\s*-\s*LIVINGROOM\s*-\s*CHAIR", "furniture-seating-chair"),
    (r"DECOR HELPER\s*-\s*CLASSIC",                   "decoration-other"),
    (r"DECOR HELPER\s*-\s*DETAIL",                    "decoration-other"),
    (r"DECOR HELPER\s*-\s*DECOR\s*-\s*VINTAGE",       "decoration-other"),
    (r"DECOR HELPER\s*-\s*DECOR",                     "decoration-other"),
    (r"DECOR HELPER\s*-\s*EXTERIOR\s*-\s*BEACH",       "nature-landscape"),
    (r"DECOR HELPER\s*-\s*EXTERIOR",                  "arch-exterior"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*BAKERY",     "commercial-restaurant"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*BANK",       "commercial-office"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*DRINK",      "commercial-restaurant"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*GARAGE",     "other-misc"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*GAS",        "commercial-other"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*HOSPITAL",   "commercial-medical"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*JAPANESE",   "rooms-living"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*PUBLIC",     "commercial-other"),
    (r"DECOR HELPER\s*-\s*INTERIOR\s*-\s*WORKSHOP",   "commercial-other"),
    (r"DECOR HELPER\s*-\s*INTERIOR",                  "rooms-other"),
    (r"DECOR HELPER\s*-\s*KITCHEN",                   "kitchen-other"),
    (r"DECOR HELPER\s*-\s*MAP",                       "materials-other"),
    (r"DECOR HELPER\s*-\s*MATERIAL\s*-\s*EXTERIOR",   "materials-other"),
    (r"DECOR HELPER\s*-\s*MATERIAL\s*-\s*LEATHER",    "materials-fabric"),
    (r"DECOR HELPER\s*-\s*MATERIAL\s*-\s*LIGHT",      "lighting-other"),
    (r"DECOR HELPER\s*-\s*MATERIAL\s*-\s*FLOOR\s*-\s*WOOD", "materials-wood"),
    (r"DECOR HELPER\s*-\s*MATERIAL",                  "materials-other"),
    (r"DECOR HELPER\s*-\s*LIVINGROOM\s*-\s*SOFA",     "furniture-seating-sofa"),
    (r"DECOR HELPER\s*-\s*LIVINGROOM\s*-\s*ARMCHAIR", "furniture-seating-armchair"),
    (r"DECOR HELPER\s*-\s*LIVINGROOM\s*-\s*CHAIR",    "furniture-seating-chair"),
    (r"DECOR HELPER\s*-\s*LIVINGROOM\s*-\s*TABLE",    "furniture-tables-coffee"),
    (r"DECOR HELPER\s*-\s*SCRIPTS",                   "other-scripts"),
    (r"DECOR HELPER",                                 "decoration-other"),

    # ─── EVERMOTION prefix ───
    (r"EVERMOTION",                                   "other-evermotion"),

    # ─── Living Room styles ───
    (r"LIVING ROOM.*(MODERN|EUROPEAN|CHINESE|NORDIC|AMERICAN|OTHER)",  "rooms-living"),
    (r"LIVING ROOM\s*SET",                            "rooms-living"),

    # ─── Bedroom styles ───
    (r"BEDROOM.*(MODERN|EUROPEAN|CHINESE|NORDIC|AMERICAN|OTHER)",      "rooms-bedroom"),
    (r"BEDROOM\s*SET",                                "rooms-bedroom"),

    # ─── Kids Room ───
    (r"CHILDROOM|CHILD\s*ROOM|KIDS?\s*ROOM|BABY\s*ROOM|CHILD",        "rooms-kids"),

    # ─── BATHROOM ───
    (r"BATHROOM\s*SET|BATHROOM\s*ACCESSOR",           "decoration-acc-bathroom"),
    (r"BATHROOM\s*FURNITURE",                         "furniture-storage-cabinet"), # Or specific bathroom furniture?
    (r"BATHROOM",                                     "rooms-bathroom"),
    (r"FAUCET|TAP\b",                                 "decoration-acc-bathroom"), # Or fixtures?
    (r"TOILET|WC\b|BIDET",                            "rooms-bathroom"), # Fixtures usually go to Bathroom generally if no specific node
    (r"SHOWER|BATH\s*TUB|BATHTUB",                    "rooms-bathroom"),
    (r"WASH\s*BASIN|BASIN|SINK",                      "rooms-bathroom"),
    (r"TOWEL",                                        "decoration-acc-bathroom"),

    # ─── Furniture – Seating ───
    (r"^SOFA$|SOFA\b|COUCH(ES)?",                     "furniture-seating-sofa"),
    (r"ARM\s*CHAIR|ARMCHAIR",                         "furniture-seating-armchair"),
    (r"OFFICE\s*CHAIR",                               "furniture-office-chair"),
    (r"DINING\s*CHAIR",                               "furniture-seating-chair"),
    (r"^CHAIR$",                                      "furniture-seating-chair"),
    (r"STOOL|BAR\s*STOOL|BAR\s*CHAIR",                "furniture-seating-stool"),
    (r"BENCH\b",                                      "furniture-seating-stool"), 
    (r"POUF|OTTOMAN|BEAN\s*BAG",                      "furniture-seating-stool"),
    (r"SEAT(ING)?",                                   "furniture-seating-other"),
    (r"ROCKING\s*CHAIR|LOUNGE\s*CHAIR|CHAISE",        "furniture-seating-armchair"),
    (r"WABI\s*SABI.*SOFA",                            "furniture-seating-sofa"),
    (r"WABI\s*SABI.*CHAIR",                           "furniture-seating-chair"),

    # ─── Furniture – Tables ───
    (r"DINING\s*TABLE",                               "furniture-tables-dining"),
    (r"COFFEE\s*TABLE|SIDE\s*TABLE|END\s*TABLE",      "furniture-tables-coffee"),
    (r"DESK\b(?!TOP)",                                "furniture-tables-desk"),
    (r"CONSOLE\b",                                    "furniture-tables-console"), # added console
    (r"TABLE\b(?!.*LAMP)(?!.*WARE)(?!.*SET)",         "furniture-tables-other"),

    # ─── Furniture – Storage ───
    (r"SHELF|SHELVING|SHELVES",                       "furniture-storage-shelving"),
    (r"WARDROBE|CUPBOARD|CLOSET",                     "furniture-storage-wardrobe"),
    (r"CHEST\b|DRAWER|DRESSER|COMMODE",               "furniture-storage-cabinet"),
    (r"CABINET\b|SIDEBOARD|BUFFET",                   "furniture-storage-cabinet"),
    (r"RACK\b(?!ET)|TV\s*STAND|TV\s*UNIT",            "furniture-storage-shelving"),
    (r"BOOK\s*CASE|BOOKSHELF|SHOE\s*RACK",            "furniture-storage-shelving"),
    (r"WABI\s*SABI.*CABINET",                         "furniture-storage-cabinet"),

    # ─── Furniture – Beds ───
    (r"^BED$|BED\b(?!ROOM)(?!SIDE)(?!DING)",          "furniture-beds-bed"),
    (r"MATTRESS|BED\s*FRAME",                         "furniture-beds-bed"),
    (r"HEADBOARD",                                    "furniture-beds-headboard"),
    (r"BUNK\s*BED|CRADLE|CRIB|BASSINET",              "furniture-beds-kids"),
    (r"BEDSIDE",                                      "furniture-tables-coffee"), # Bedside table

    # ─── Furniture – Office ───
    (r"OFFICE\s*FURNITURE|OFFICE\s*SET",              "furniture-office-other"),
    (r"OFFICE\s*DESK",                                "furniture-office-desk"),
    (r"BOOK\s*STAND|FILE\s*CABINET",                  "furniture-office-other"),

    # ─── Furniture – Outdoor ───
    (r"OUTDOOR\s*FURNITURE|GARDEN\s*FURNITURE|PATIO",  "furniture-outdoor"),
    (r"PERGOLA|GAZEBO|HAMMOCK|SWING",                 "furniture-outdoor"),
    (r"PLAYGROUND|UMBRELLA\s*(?!STAND)",               "furniture-outdoor"),

    # ─── Furniture – Other / General ───
    (r"^FURNITURE$|FURNITURE\s*-\s*OTHER",             "furniture-other"),
    (r"SCREEN\s*PARTITION|ROOM\s*DIVIDER|PARTITION",   "furniture-other"),
    (r"COAT\s*RACK|HANGER\s*(?!.*CLOTH)",              "furniture-other"),
    (r"WABI\s*SABI.*FURNITURE",                        "furniture-other"),

    # ─── Lighting ───
    (r"PENDANT\s*LIGHT|CHANDELIER|HANGING\s*LAMP",    "lighting-ceiling"),
    (r"CEILING\s*(LIGHT|LAMP|FAN)",                   "lighting-ceiling"),
    (r"SPOT\s*LIGHT|TRACK\s*LIGHT|RECESSED",          "lighting-ceiling"),
    (r"FLOOR\s*LAMP|STANDING\s*LAMP|FLOOR\s*LIGHT",   "lighting-floor"),
    (r"WALL\s*LAMP|WALL\s*LIGHT|SCONCE",              "lighting-wall"),
    (r"TABLE\s*LAMP|DESK\s*LAMP|READING\s*LAMP",      "lighting-table"),
    (r"NEON|LED\s*(STRIP|LIGHT)|CANDLE\s*LIGHT",      "lighting-decorative"),
    (r"STREET\s*LIGHT|GARDEN\s*LIGHT|OUTDOOR.*LIGHT", "lighting-outdoor"),
    (r"^LIGHTING$|LIGHTING\s*-\s*OTHER|DECORATION\s*-\s*LIGHTING", "lighting-other"),

    # ─── Decoration ───
    (r"CARPET|RUG\b(?!BY)",                           "decoration-textiles-carpets"),
    (r"CURTAIN|DRAPE|BLIND\b",                        "decoration-textiles-curtains"),
    (r"PILLOW|CUSHION|THROW\b",                       "decoration-textiles-pillows"),
    (r"MIRROR\b",                                     "decoration-wall-mirror"),
    (r"FRAME\b|PICTURE\b|PAINTING|POSTER|WALL\s*ART", "decoration-wall-art"),
    (r"SCULPTURE|FIGURINE|STATUE",                    "decoration-wall-art"),
    (r"VASE|POTTERY|CERAMIC|PLANTER",                 "decoration-acc-vases"),
    (r"CLOCK\b|WATCH(ES)?(?!.*SMART)",                "decoration-wall-clock"),
    (r"CANDLE|CANDLE\s*HOLDER|LANTERN",               "decoration-acc-candles"),
    (r"BOOK\b(?!.*CASE)(?!.*SHELF)(?!.*STAND)|MAGAZINE", "decoration-acc-books"),
    (r"^DECORATION$|DECORATION\s*-\s*OTHER",          "decoration-other"),
    (r"DECORATION\s*-\s*FRAME",                       "decoration-wall-art"),
    (r"DECORATION\s*-\s*MIRROR",                      "decoration-wall-mirror"),
    (r"DECOR(?!.*HELPER)",                            "decoration-other"),

    # ─── Kitchen & Dining ───
    (r"KITCHEN\s*(SET|ACCESSOR|FURNITURE|EQUIPMENT|CABINET)", "kitchen-other"),
    (r"^KITCHEN$|KITCHEN\s*SETS?",                    "kitchen-other"),
    (r"OVEN|MICROWAVE|DISHWASHER|DISH\s*WASHER",      "kitchen-appliances"),
    (r"FRIDGE|REFRIGERATOR|FREEZER",                  "kitchen-appliances"),
    (r"BLENDER|MIXER|COFFEE\s*MACHINE|TOASTER",       "kitchen-appliances"),
    (r"EXHAUST|RANGE\s*HOOD|HOOD\b|COOKTOP|STOVE",    "kitchen-appliances"),
    (r"TABLEWARE|DINNERWARE|PLATE|BOWL|CUP|GLASS\b|MUG", "kitchen-tableware"),
    (r"CUTLERY|KNIFE|FORK|SPOON|CHOPSTICK",           "kitchen-tableware"),
    (r"POT\b|PAN\b|WOK|COOKWARE|KETTLE",              "kitchen-cookware"),
    (r"FOOD\b|FRUIT|VEGETABLE|BREAD|CAKE|WINE|BEER|DRINK|BEVERAGE", "kitchen-food"),
    (r"BOTTLE\b",                                     "kitchen-food"),

    # ─── Architecture ───
    (r"DOOR\b(?!.*MAT)(?!.*BELL)(?!.*STOP)",          "arch-doors"),
    (r"WINDOW\b(?!.*BLIND)",                          "arch-windows"),
    (r"STAIR|RAILING|BALUSTRADE|HANDRAIL|BANISTER",   "arch-stairs"),
    (r"WALL\s*PANEL|PANEL|WAINSCOT|BASEBOARD",        "arch-walls"),
    (r"COLUMN\b|CORNICE|MOLDING|MOULDING|PLASTER\b",  "arch-columns"),
    (r"FACADE|EXTERIOR\s*WALL|CLADDING",              "arch-exterior"),
    (r"FENCE|GATE\b(?!WAY)|RAILING\s*(?!STAIR)",      "arch-exterior"), # Fence under exterior
    (r"ROOF|GUTTER|CHIMNEY|SKYLIGHT",                 "arch-exterior"),
    (r"FIREPLACE|MANTEL|HEARTH",                      "arch-other"),
    (r"RADIATOR|HEATER|AIR\s*CONDITION",              "arch-other"),

    # ─── Nature & Plants ───
    (r"^PLANTS?$|INDOOR\s*PLANT|HOUSE\s*PLANT|POT\s*PLANT|POTTED",  "nature-plants"),
    (r"TREE\b(?!.*HOUSE)",                            "nature-trees"),
    (r"FLOWER|BOUQUET|FLORAL",                        "nature-flowers"),
    (r"GRASS\b|LAWN|HEDGE|BUSH(?!IDO)|SHRUB",         "nature-grass"),
    (r"GARDEN|LANDSCAPE|ROCK\b|STONE\s*(?!TILE)",     "nature-landscape"),
    (r"NATURE|OUTDOOR(?!.*FURNITURE)(?!.*LIGHT)",     "nature-other"),

    # ─── Technology ───
    (r"COMPUTER|LAPTOP|PC\b|MONITOR|iMAC|KEYBOARD",  "tech-computers"),
    (r"TV\b|TELEVISION|DISPLAY|PROJECTOR|SCREEN\b(?!.*PARTITION)", "tech-tv"),
    (r"SPEAKER|HEADPHONE|AUDIO|RADIO|TURNTABLE|PLAYER", "tech-audio"),
    (r"PHONE|SMARTPHONE|TABLET|iPAD",                 "tech-other"),
    (r"WASHING\s*MACHINE|DRYER|IRON\b|VACUUM|FAN\b",  "tech-appliances"),
    (r"ROBOT\b|DRONE|CAMERA|PRINTER|SCANNER",         "tech-other"),

    # ─── Vehicles ───
    (r"CAR\b|AUTOMOBILE|SEDAN|SUV\b|TRUCK(?!.*FOOD)", "vehicles-cars"),
    (r"BIKE|BICYCLE|MOTORCYCLE|SCOOTER",              "vehicles-bikes"),
    (r"VEHICLE|BUS\b|TRAIN|BOAT|SHIP|AIRCRAFT|AIRPLANE|HELICOPTER", "vehicles-other"), # No deep vehicles requested

    # ─── Materials ───
    (r"^TILE$|TILES?\b|CERAMIC\s*TILE|FLOOR\s*TILE",  "materials-tile"),
    (r"PARQUET|FLOORING|LAMINATE\s*FLOOR",             "materials-wood"),
    (r"WOOD\s*TEXTURE|WOOD\s*PANEL|TIMBER",            "materials-wood"),
    (r"MARBLE|GRANITE|STONE\s*TILE|ONYX|TRAVERTINE",  "materials-stone"),
    (r"METAL\s*TEXTURE|STEEL|IRON\s*(?!BOARD)|BRASS|COPPER", "materials-metal"),
    (r"FABRIC\s*TEXTURE|CLOTH\s*TEXTURE|LEATHER\s*TEXTURE", "materials-fabric"),
    (r"^MATERIAL$|MATERIAL\s|TEXTURE\b|WALLPAPER\b",  "materials-other"),

    # ─── Clothing ───
    (r"SHOE|SNEAKER|BOOT\b|HEEL\b|SANDAL",           "clothing-shoes"),
    (r"BAG\b|HANDBAG|BACKPACK|LUGGAGE|SUITCASE",      "clothing-bags"),
    (r"CLOTH(ES|ING)|GARMENT|DRESS\b|SHIRT|JACKET|COAT(?!.*RACK)", "clothing-other"),
    (r"HAT\b|CAP\b|HELMET|GLOVE",                     "clothing-other"),

    # ─── Characters ───
    (r"PEOPLE|PERSON|HUMAN|MAN\b|WOMAN|CHILD(?!ROOM)|BABY(?!.*ROOM)", "characters-people"),
    (r"ANIMAL|DOG\b|CAT\b|HORSE|BIRD|FISH\b|PET\b",  "characters-animals"),
    (r"CHARACTER|AVATAR|MANNEQUIN",                   "characters-other"),
    (r"WEAPON",                                       "characters-other"),

    # ─── Commercial ───
    (r"SHOP\b|STORE\b|RETAIL|DISPLAY\s*CASE|SHOWCASE|RECEPTION", "commercial-retail"),
    (r"RESTAURANT|CAFE|BAR\b(?!.*STOOL)(?!.*CHAIR)|KITCHEN\s*COMMERCIAL", "commercial-restaurant"),
    (r"BEAUTY|SPA\b|SALON",                           "commercial-beauty"),
    (r"HOTEL|RESORT|LOBBY",                           "commercial-hotel"),
    (r"HOSPITAL|CLINIC|MEDICAL|DENTAL",               "commercial-medical"),
    (r"GYM|FITNESS|SPORT",                            "commercial-other"),
    (r"SCHOOL|CLASSROOM|LIBRARY|UNIVERSITY",          "commercial-other"),
    (r"PUBLIC\s*COMMERCE|COMMERCE\s*SPACE",            "commercial-other"),

    # ─── Scenes & Renders ───
    (r"SCENES?\s*-\s*LIVING",                         "scenes-living"),
    (r"SCENES?\s*-\s*BEDROOM",                        "scenes-bedroom"),
    (r"SCENES?\s*-\s*KITCHEN",                        "scenes-kitchen"),
    (r"SCENES?\s*-\s*BATHROOM",                       "scenes-bathroom"),
    (r"SCENES?\s*-\s*APARTMENT",                      "scenes-apartment"),
    (r"SCENES?\s*-\s*EXTERIOR",                       "scenes-exterior"),
    (r"SCENES?\s*-\s*COMMERCIAL",                     "scenes-commercial"),
    (r"SCENES?\s*-\s*GAME",                           "scenes-games"),
    (r"HDRI|PANORAMA",                                "scenes-hdri"),
    (r"^SCENE$",                                      "scenes-other"),
    (r"CORONA\s*SCENES?",                             "scenes-other"),
    (r"3D\s*SCENES?",                                 "scenes-other"),

    # ─── FURNITURE prefix (from 3dskyfree.com) ───
    (r"FURNITURE\s*-\s*AMRCHAIR|FURNITURE\s*-\s*ARMCHAIR", "furniture-seating-armchair"),
    (r"FURNITURE\s*-\s*CHAIR",                        "furniture-seating-chair"),
    (r"FURNITURE\s*-\s*BENCH",                        "furniture-seating-stool"),
    (r"FURNITURE\s*-\s*TABLE\s*AND\s*CHAIR",          "furniture-tables-dining"),
    (r"FURNITURE\s*-\s*BEDSIDE",                      "furniture-tables-coffee"),
    (r"FURNITURE\s*-\s*BED\b",                        "furniture-beds-bed"),
    (r"FURNITURE\s*-\s*CHILDBED",                     "furniture-beds-kids"),
    (r"FURNITURE\s*-\s*CONSOLE",                      "furniture-tables-console"),
    (r"FURNITURE\s*-\s*HALLWAY",                      "furniture-other"),
    (r"FURNITURE\s*-\s*OFFICE",                       "furniture-office-other"),
    (r"FURNITURE\s*-\s*RATTAN",                       "furniture-other"),
    (r"FURNITURE\s*-\s*CLASSIC",                      "furniture-other"),
    (r"FURNITURE\s*-\s*PHONG",                        "furniture-other"),
    (r"FURNITURE\s*3D|^FURNITURE\s*3D",               "furniture-other"),
    (r"Full\s*furniture\s*set",                       "furniture-other"),
    (r"Other\s*Furniture",                            "furniture-other"),
    (r"WOODEN\s*CHAIR",                               "furniture-seating-chair"),
    (r"FURNITURE\s*-\s*MODERN\s*SOFA",                "furniture-seating-sofa"),
    (r"FURNITURE\s*-\s*SOFA\s*TABLE",                 "furniture-tables-coffee"),
    (r"FURNITURE\s*-\s*SOFA",                         "furniture-seating-sofa"),
    (r"FURNITURE\s*-\s*TABLE\s*CHAIR",                "furniture-tables-dining"),
    (r"TABLE\s*.\s*CHAIR",                            "furniture-tables-dining"),

    # ─── ARCHITECTURE prefix ───
    (r"ARCHITECTURE\s*-\s*BUILDING",                  "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*ENVIRO",                    "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*EXTERIOR",                  "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*FACADE",                    "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*URBAN",                     "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*PLAYGROUND",                "furniture-outdoor"),
    (r"ARCHITECTURE\s*-\s*PAVING",                    "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*BABECUE|ARCHITECTURE\s*-\s*BBQ", "arch-other"),
    (r"ARCHITECTURE\s*-\s*FENCE",                     "arch-exterior"),
    (r"ARCHITECTURE\s*-\s*OTHER",                     "arch-other"),
    (r"^Architecture$",                               "arch-other"),
    (r"Other\s*Architecture",                         "arch-other"),
    (r"EXTERIORS.*ARCHITECTURE",                      "arch-exterior"),
    (r"PILLAR\s*3D",                                  "arch-columns"),

    # ─── WABI SABI prefix ───
    (r"WABI\s*SABI\s*-\s*LAMP",                       "lighting-decorative"),
    (r"WABI\s*SABI\s*-\s*PLANT",                      "nature-plants"),
    (r"WABI\s*SABI\s*-\s*DOOR",                       "arch-doors"),
    (r"WABI\s*SABI\s*-\s*BEDSIDE",                    "furniture-tables-coffee"),
    (r"WABI\s*SABI\s*STYLE",                          "rooms-other"),

    # ─── LIVING ROOM additional styles ───
    (r"LIVING\s*ROOM\s*-\s*(WABI|MINIMALIST|ITALIAN|FRENCH|JAPANESE)", "rooms-living"),

    # ─── BEDROOM additional styles ───
    (r"BEDROOM\s*-\s*(WABI|MINIMALIST)",              "rooms-bedroom"),
    (r"BEDROOM\s*BENCH",                              "furniture-seating-stool"),

    # ─── Catch-all OTHER ───
    (r"OTHER\s*MODEL",                                "other-misc"),
    (r"MISCELLANEOUS|MISC\b",                         "other-misc"),
    (r"Scandinavian",                                 "rooms-other"),
]

# Compile all rules once
COMPILED_RULES = [(re.compile(pat, re.IGNORECASE), slug) for pat, slug in KEYWORD_RULES]


def classify_category(name: str) -> str:
    """Return the taxonomy slug for a category name using keyword rules."""
    for pattern, tax_slug in COMPILED_RULES:
        if pattern.search(name):
            return tax_slug
    return "other-misc"  # Fallback


def build_taxonomy(conn):
    """Build the full taxonomy mapping from the categories table."""
    conn.row_factory = sqlite3.Row
    # 1. Fetch all categories
    categories = conn.execute(
        "SELECT id, name, slug, parent_id, post_count FROM categories ORDER BY name"
    ).fetchall()
    
    print(f"📊 Found {len(categories)} categories to classify\n")

    # 2. Build taxonomy node lookup (recursive)
    tax_nodes = {} # slug → dict

    def traverse(nodes, parent_slug=None, level=0):
        for idx, node in enumerate(nodes):
            slug = node["slug"]
            tax_nodes[slug] = {
                "name": node["name"],
                "slug": slug,
                "parent_slug": parent_slug,
                "icon": node.get("icon"),
                "dynamic_tag_source": node.get("dynamic_tag_source"),
                "sort_order": idx,
                "children": [], # Will store slugs of children
                "level": level
            }
            if parent_slug:
                tax_nodes[parent_slug]["children"].append(slug)
            
            if "children" in node:
                traverse(node["children"], slug, level + 1)

    traverse(TAXONOMY_TREE)
    
    # 3. Classify each category
    mappings = []
    
    for cat in categories:
        tax_slug = classify_category(cat["name"])
        mappings.append((tax_slug, cat["slug"], cat["name"], cat["post_count"]))

    # 4. Compute Counts
    counts = {}
    for tax_slug, _, _, post_count in mappings:
        counts[tax_slug] = counts.get(tax_slug, 0) + post_count
    
    # Propagate to parents
    parent_counts = counts.copy()

    # Get depth for each node
    depths = {}
    def get_depth(slug):
        if slug not in tax_nodes: return 0
        node = tax_nodes[slug]
        if not node["parent_slug"]: return 0
        return 1 + get_depth(node["parent_slug"])
    
    for slug in tax_nodes:
        depths[slug] = get_depth(slug)
    
    max_depth = max(depths.values()) if depths else 0
    
    for d in range(max_depth, 0, -1):
        for slug, depth in depths.items():
            if depth == d:
                node = tax_nodes[slug]
                p_slug = node["parent_slug"]
                if p_slug:
                    parent_counts[p_slug] = parent_counts.get(p_slug, 0) + parent_counts.get(slug, 0)
    
    return tax_nodes, mappings, counts, parent_counts


def preview(tax_nodes, mappings, counts, parent_counts):
    print("=" * 70)
    print("TAXONOMY PREVIEW (Deep Hierarchical)")
    print("=" * 70)

    by_tax = {}
    for tax_slug, cat_slug, cat_name, pc in mappings:
        by_tax.setdefault(tax_slug, []).append((cat_name, cat_slug, pc))
    
    def print_node_recursive(slug, indent=0):
        node = tax_nodes[slug]
        total = parent_counts.get(slug, 0)
        direct_cats = by_tax.get(slug, [])
        prefix = " " * indent * 4
        
        name_str = f"{node['name']}"
        if node.get('dynamic_tag_source'):
            name_str += f" [DYNAMIC: {node['dynamic_tag_source']}]"
        
        print(f"\n{prefix}├── {name_str} — {total:,} posts")
        if direct_cats:
            print(f"{prefix}│   ({len(direct_cats)} mapped categories)")
            for cat_name, cat_slug, pc in sorted(direct_cats, key=lambda x: -x[2])[:3]:
                 print(f"{prefix}│   → {cat_name[:40]:40s} ({pc:,})")
            if len(direct_cats) > 3:
                print(f"{prefix}│     ... and {len(direct_cats)-3} more")

        for child_slug in node["children"]:
            print_node_recursive(child_slug, indent + 1)

    # Print top level nodes
    roots = [s for s, n in tax_nodes.items() if not n["parent_slug"]]
    for root in roots:
        print_node_recursive(root)
    
    # Unclassified check
    unmapped = by_tax.get("other-misc", [])
    if unmapped:
        print(f"\n{'='*60}")
        print(f"⚠️  FALLBACK (other-misc): {len(unmapped)} categories")
        for cat_name, cat_slug, pc in sorted(unmapped, key=lambda x: -x[2]):
            print(f"    [{pc:>5}] {cat_name}")

    # Summary
    total_mapped = len(mappings)
    total_posts = sum(pc for _, _, _, pc in mappings)
    used_tax = len(set(ts for ts, _, _, _ in mappings))
    print(f"\n{'='*60}")
    print(f"✅ SUMMARY")
    print(f"   Categories mapped: {total_mapped}")
    print(f"   Total posts covered: {total_posts:,}")
    print(f"   Taxonomy nodes used: {used_tax}")

def save_preview_json(tax_nodes, mappings, counts, parent_counts):
    """Save full taxonomy preview as JSON."""
    by_tax = {}
    for tax_slug, cat_slug, cat_name, pc in mappings:
        by_tax.setdefault(tax_slug, []).append({
            "name": cat_name, "slug": cat_slug, "posts": pc
        })

    def build_tree_recursive(nodes):
        res = []
        for slug in nodes:
            node = tax_nodes[slug]
            # Recursively build children
            children_slugs = node["children"]
            children_data = build_tree_recursive(children_slugs)
            
            # Retrieve list of dicts and sort
            direct_cats = sorted(by_tax.get(slug, []), key=lambda x: -x["posts"])
            cat_list = direct_cats

            data = {
                "name": node["name"],
                "slug": slug,
                "icon": node.get("icon"),
                "dynamic_tag_source": node.get("dynamic_tag_source"),
                "total_posts": parent_counts.get(slug, 0),
                "direct_categories": cat_list,
            }
            if children_data:
                data["children"] = children_data
            res.append(data)
        return res

    roots = [s for s, n in tax_nodes.items() if not n["parent_slug"]]
    tree = build_tree_recursive(roots)

    with open(PREVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Preview saved to {PREVIEW_FILE}")


def apply_taxonomy(conn, tax_nodes, mappings):
    """Create taxonomy tables and insert data."""
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            parent_id INTEGER DEFAULT 0,
            icon TEXT,
            dynamic_tag_source TEXT,
            sort_order INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS taxonomy_mapping (
            taxonomy_id INTEGER NOT NULL,
            category_slug TEXT NOT NULL,
            PRIMARY KEY (taxonomy_id, category_slug)
        )
    """)
    
    # Check if dynamic_tag_source column exists, add if missing (migration)
    try:
        cursor.execute("SELECT dynamic_tag_source FROM taxonomy LIMIT 1")
    except sqlite3.OperationalError:
        print("⚠️ Adding missing column: dynamic_tag_source")
        cursor.execute("ALTER TABLE taxonomy ADD COLUMN dynamic_tag_source TEXT")
    
    slug_to_id = {}
    
    def insert_recursive(slug):
        if slug in slug_to_id: return
        node = tax_nodes[slug]
        parent_id = 0
        if node["parent_slug"]:
            if node["parent_slug"] not in slug_to_id:
                insert_recursive(node["parent_slug"])
            parent_id = slug_to_id[node["parent_slug"]]
        
        # Upsert logic:
        cursor.execute("""
            INSERT INTO taxonomy (name, slug, parent_id, icon, dynamic_tag_source, sort_order) 
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                parent_id=excluded.parent_id,
                icon=excluded.icon,
                dynamic_tag_source=excluded.dynamic_tag_source,
                sort_order=excluded.sort_order
        """, (node["name"], slug, parent_id, node["icon"], node["dynamic_tag_source"], node["sort_order"]))
        
        # Retrieve ID
        cursor.execute("SELECT id FROM taxonomy WHERE slug = ?", (slug,))
        slug_to_id[slug] = cursor.fetchone()[0]
        
        for child_slug in node["children"]:
            insert_recursive(child_slug)

    roots = [s for s, n in tax_nodes.items() if not n["parent_slug"]]
    for root in roots:
        insert_recursive(root)

    print(f"✅ Created/Updated {len(slug_to_id)} taxonomy nodes")

    # Insert mappings
    count = 0
    for tax_slug, cat_slug, _, _ in mappings:
        if tax_slug not in slug_to_id:
             if tax_slug == "other-misc":
                 tax_id = slug_to_id.get("other-misc")
                 if not tax_id: continue
             else:
                 continue
        else:
            tax_id = slug_to_id[tax_slug]
            
        cursor.execute("INSERT OR IGNORE INTO taxonomy_mapping (taxonomy_id, category_slug) VALUES (?, ?)", (tax_id, cat_slug))
        count += 1
    
    conn.commit()
    print(f"✅ Inserted {count} mappings")

def reset_taxonomy(conn):
    """Drop and rebuild taxonomy tables."""
    conn.execute("DROP TABLE IF EXISTS taxonomy_mapping")
    conn.execute("DROP TABLE IF EXISTS taxonomy")
    conn.commit()
    print("🗑️  Dropped existing taxonomy tables")


def main():
    parser = argparse.ArgumentParser(description="Build smart taxonomy for 3DSkyFree")
    parser.add_argument("--dry-run", action="store_true", help="Preview without modifying DB")
    parser.add_argument("--apply", action="store_true", help="Create tables and insert data")
    parser.add_argument("--reset", action="store_true", help="Drop and rebuild taxonomy tables")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Usage: python build_taxonomy.py --dry-run  OR  --apply [--reset]")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    if args.apply and args.reset:
        reset_taxonomy(conn)

    tax_nodes, mappings, counts, parent_counts = build_taxonomy(conn)
    preview(tax_nodes, mappings, counts, parent_counts)
    save_preview_json(tax_nodes, mappings, counts, parent_counts)

    if args.apply:
        apply_taxonomy(conn, tax_nodes, mappings)

    conn.close()


if __name__ == "__main__":
    main()
