"""
Domain rule: paid vs free tier classification.

Single source of truth — all other modules should call is_paid()
rather than checking PAID_CATEGORY_SLUGS directly.
"""
from ..constants import PAID_CATEGORY_SLUGS


def is_paid(category_slug: str | None) -> bool:
    """Return True if the category slug belongs to the paid tier."""
    return bool(category_slug) and category_slug in PAID_CATEGORY_SLUGS


def annotate_tier(item: dict) -> dict:
    """Mutate an item dict to add a 'tier' string field. Returns the dict."""
    item["tier"] = "Paid" if is_paid(item.get("category_slug")) else "Free"
    return item
