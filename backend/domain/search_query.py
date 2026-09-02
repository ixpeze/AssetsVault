"""
SearchQuery — validated value object representing a single search request.

All validation and defaults live here. Application and persistence layers
consume this object; they never touch raw request params.
"""
from dataclasses import dataclass, field
from typing import Optional
from ..search.fts import build_expression


_SORT_MAP = {
    "relevance":  "rank ASC",
    "newest":     "items.id DESC",
    "oldest":     "items.id ASC",
    "title_asc":  "items.title ASC",
    "title_desc": "items.title DESC",
    "has_gdrive": "CASE WHEN items.gdrive_link IS NOT NULL AND items.gdrive_link != '' THEN 0 ELSE 1 END, items.id DESC",
}


@dataclass
class SearchQuery:
    # Text search
    q: str = ""

    # Category / taxonomy filters
    category: str = ""
    taxonomy: str = ""

    # Attribute filters
    tier: str = ""          # "Free" | "Paid" | ""
    tag: str = ""

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
        # Default to relevance ranking whenever a search query is active unless explicitly asked for another sort
        if self.q and self.sort == "newest":
            self.sort = "relevance"

    @property
    def fts_expression(self) -> str:
        """Build FTS5 MATCH expression with sanitized prefix wildcards."""
        return build_expression(self.q)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def order_by(self) -> str:
        return _SORT_MAP.get(self.sort, "items.id DESC")

