"""
SearchQuery — validated value object representing a single search request.

All validation and defaults live here. Application and persistence layers
consume this object; they never touch raw request params.
"""
from dataclasses import dataclass, field
from typing import Optional


_SORT_MAP = {
    "newest":    "id DESC",
    "oldest":    "id ASC",
    "title_asc": "title ASC",
    "title_desc":"title DESC",
    "has_gdrive":"CASE WHEN gdrive_link IS NOT NULL AND gdrive_link != '' THEN 0 ELSE 1 END, id DESC",
}


@dataclass
class SearchQuery:
    # Text search
    q: str = ""
    semantic_q: str = ""

    # Category / taxonomy filters
    category: str = ""
    taxonomy: str = ""

    # Attribute filters
    tier: str = ""          # "Free" | "Paid" | ""
    tag: str = ""
    color_hex: str = ""

    # Exclude (NOT) filters
    exclude_tag: str = ""        # tag name to exclude
    exclude_category: str = ""   # category slug to exclude

    # Multi-tag AND/OR filter
    tags: str = ""           # comma-separated list of tag names
    tags_mode: str = "or"   # "and" | "or"

    # Boolean filters
    fav: bool = False
    has_gdrive: bool = False
    no_gdrive: bool = False
    has_image: bool = False
    no_image: bool = False
    has_size: bool = False
    no_size: bool = False
    exclude_q: str = ""      # terms to exclude from results (space-separated)

    # Quick-view filters
    untagged: bool = False   # items with zero tags attached
    missing: bool = False    # items with no image (local or remote)

    # Collection scope
    collection_id: Optional[int] = None

    # Pagination
    page: int = 1
    per_page: int = 24
    sort: str = "newest"

    def __post_init__(self):
        self.page = max(1, self.page)
        self.per_page = min(100, max(1, self.per_page))
        if self.color_hex and not self.color_hex.startswith("#"):
            self.color_hex = "#" + self.color_hex

    @property
    def fts_expression(self) -> str:
        """Build FTS5 MATCH expression with prefix wildcards."""
        if not self.q:
            return ""
        terms = [w for w in self.q.split() if w.strip()]
        return " ".join(f'"{w}"*' for w in terms)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def order_by(self) -> str:
        return _SORT_MAP.get(self.sort, "id DESC")
