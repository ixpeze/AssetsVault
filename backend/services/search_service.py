"""
backend.services.search_service — cached search facade.

Wraps application.search.search_assets with a 30-second TTL cache
via core.cache.response_cache. Cache is invalidated when a pipeline
task completes (subscribed to "pipeline_completed" in app factory).

Usage:
    from backend.services.search_service import search_service
    result = search_service.search(conn, query)
    search_service.invalidate_cache()   # also called automatically on pipeline_completed
"""
import logging
from ..domain.search_query import SearchQuery

log = logging.getLogger(__name__)

_TTL = 30  # seconds


def _cache_key(query: SearchQuery) -> str:
    """Build a stable cache key from all significant SearchQuery fields."""
    parts = [
        f"q={query.q}",
        f"cat={query.category}",
        f"tax={query.taxonomy}",
        f"tier={query.tier}",
        f"tag={query.tag}",
        f"fav={query.fav}",
        f"gdrive={query.has_gdrive},{query.no_gdrive}",
        f"img={query.has_image},{query.no_image}",
        f"size={query.has_size},{query.no_size}",
        f"xq={query.exclude_q}",
        f"xtag={query.exclude_tag}",
        f"xcat={query.exclude_category}",
        f"tags={query.tags}:{query.tags_mode}",
        f"coll={query.collection_id}",
        f"untagged={query.untagged}",
        f"missing={query.missing}",
        f"render={query.render_engine}",
        f"maxv={query.max_version}",
        f"sizes={query.min_size}:{query.max_size}",
        f"light={query.lighting}",
        f"page={query.page}",
        f"per={query.per_page}",
        f"sort={query.sort}",
    ]
    return "search:" + "|".join(parts)


class SearchService:
    def search(self, conn, query: SearchQuery) -> dict:
        from ..core.cache import response_cache
        from ..application import search as search_uc

        key = _cache_key(query)
        cached = response_cache.get(key)
        if cached is not None:
            log.debug("[SearchService] Cache hit: %s", key[:80])
            return cached

        result = search_uc.search_assets(conn, query)
        response_cache.set(key, result, ttl=_TTL)
        return result

    def invalidate_cache(self, **kwargs) -> None:
        from ..core.cache import response_cache
        count = response_cache.invalidate_prefix("search:")
        log.info("[SearchService] Invalidated %d search cache entries", count)


# Module-level singleton
search_service = SearchService()
