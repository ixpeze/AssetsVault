import re

# ─── Tag-based category → taxonomy mapping rules ──────────────────────
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

    # ─── Characters ───
    (r"PEOPLE|PERSON|HUMAN|MAN\b|WOMAN|CHILD(?!ROOM)|BABY(?!.*ROOM)", "characters-people"),
    (r"ANIMAL|DOG\b|CAT\b|HORSE|BIRD|FISH\b|PET\b",  "characters-animals"),
    (r"CHARACTER|AVATAR|MANNEQUIN",                   "characters-other"),
    (r"WEAPON",                                       "characters-other"),

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


def classify_tags(tags: list) -> str:
    """Return the first matching taxonomy slug for a list of tags."""
    if not tags:
        return None
        
    for pattern, tax_slug in COMPILED_RULES:
        # Check if any tag matches the pattern
        for tag in tags:
            if pattern.search(tag):
                return tax_slug
    
    return None
