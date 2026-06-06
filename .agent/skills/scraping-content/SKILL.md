---
name: scraping-content
description: Scrapes content from 3dskyfree.com. Use when the user wants to download 3D models, textures, or update the local database of assets.
---

# Scraping Content

## When to use this skill
- When the user wants to "scrape" or "download" models from 3dskyfree.
- When the user wants to update the database with new items.
- When the user specifically mentions `scraper.py`, `scrape_all_free.ps1`, or `scrape_all_paid.ps1`.

## Workflow
1. **Check Requirements**: Ensure `requirements.txt` is installed and `cookies.json` exists (for paid content).
2. **Select Mode**:
    - **Single Category**: Use `scraper.py` directly.
    - **Bulk Free**: Use `scrape_all_free.ps1`.
    - **Bulk Paid**: Use `scrape_all_paid.ps1`.
3. **Run Scraper**: Execute the chosen command.
4. **Verify**: Check `data/[category_slug]` for downloaded images and `3dskyfree.db` for records.

## Instructions

### Authentication (Paid Content)
To scrape paid content or download full-resolution archives, you need valid cookies.
1. Run `python export_cookies.py` and follow the instructions to paste cookies.
2. Ensure `cookies.json` is created in the root directory.

### Single Category scraping
Use `scraper.py` for granular control.
```bash
# List all categories to find slugs
python scraper.py --list-categories

# Scrape a specific category (Free)
python scraper.py --category [slug]

# Scrape a specific category (Paid - requires cookies)
python scraper.py --category [slug] --cookies

# Common options
python scraper.py --category [slug] --limit 10   # Only first 10 items
python scraper.py --category [slug] --resume     # Resume if interrupted
python scraper.py --category [slug] --skip-images # Metadata only
```

### Bulk Scraping
Use PowerShell scripts for mass collection.
```powershell
# Scrape all FREE categories
.\scrape_all_free.ps1

# Scrape all PAID categories (metadata + images only)
# Note: Google Drive links for paid content require manual interaction or the Bookmarklet
.\scrape_all_paid.ps1
```

## Resources
- [scraper.py](file:///g:/AI/3DSkyFree/scraper.py)
- [scrape_all_free.ps1](file:///g:/AI/3DSkyFree/scrape_all_free.ps1)
- [scrape_all_paid.ps1](file:///g:/AI/3DSkyFree/scrape_all_paid.ps1)
