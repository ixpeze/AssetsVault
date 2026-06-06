"""Generate batch scraping commands from category classification."""
import json
from pathlib import Path

data = json.load(open("category_classification.json", "r", encoding="utf-8"))

free = sorted(data["free"], key=lambda c: c["name"])
paid = sorted(data["paid"], key=lambda c: c["name"])

print(f"{'='*70}")
print(f"  CLASSIFICATION SUMMARY")
print(f"{'='*70}")
print(f"  🟢 Free:  {len(free)} categories ({data['summary']['free_posts']:,} posts)")
print(f"  🔴 Paid:  {len(paid)} categories ({data['summary']['paid_posts']:,} posts)")
print()

# ---- Free categories list ----
print(f"\n{'='*70}")
print(f"  🟢 FREE CATEGORIES ({len(free)})")
print(f"{'='*70}")
for c in free:
    print(f"  {c['name'][:50]:<50} slug={c['slug']:<45} posts={c['post_count']}")

# ---- Paid categories list ----
print(f"\n{'='*70}")
print(f"  🔴 PAID CATEGORIES ({len(paid)})")
print(f"{'='*70}")
for c in paid:
    print(f"  {c['name'][:50]:<50} slug={c['slug']:<45} posts={c['post_count']}")

# ---- Generate batch commands ----
# Free: batch of 30 categories per command using shell loop
free_slugs = [c["slug"] for c in free]
paid_slugs = [c["slug"] for c in paid]

# Write batch scripts
with open("scrape_all_free.ps1", "w", encoding="utf-8") as f:
    f.write("# Auto-generated: Scrape ALL free categories\n")
    f.write(f"# {len(free_slugs)} categories, {data['summary']['free_posts']:,} total posts\n")
    f.write("# Usage: .\\scrape_all_free.ps1\n\n")
    f.write('$categories = @(\n')
    for slug in free_slugs:
        f.write(f'    "{slug}"\n')
    f.write(')\n\n')
    f.write('foreach ($cat in $categories) {\n')
    f.write('    Write-Host ""`n"🔄 Scraping: $cat" -ForegroundColor Cyan\n')
    f.write('    python scraper.py --category $cat --delay 2 --resume\n')
    f.write('    if ($LASTEXITCODE -ne 0) {\n')
    f.write('        Write-Host "⚠️ Error on $cat, continuing..." -ForegroundColor Yellow\n')
    f.write('    }\n')
    f.write('}\n')
    f.write('Write-Host "`n✅ All free categories done!" -ForegroundColor Green\n')

with open("scrape_all_paid.ps1", "w", encoding="utf-8") as f:
    f.write("# Auto-generated: Scrape ALL paid categories (metadata + images only)\n")
    f.write(f"# {len(paid_slugs)} categories, {data['summary']['paid_posts']:,} total posts\n")
    f.write("# Drive links must be captured manually via bookmarklet\n")
    f.write("# Usage: .\\scrape_all_paid.ps1\n\n")
    f.write('$categories = @(\n')
    for slug in paid_slugs:
        f.write(f'    "{slug}"\n')
    f.write(')\n\n')
    f.write('foreach ($cat in $categories) {\n')
    f.write('    Write-Host "`n🔄 Scraping: $cat" -ForegroundColor Cyan\n')
    f.write('    python scraper.py --category $cat --cookies --delay 2 --resume\n')
    f.write('    if ($LASTEXITCODE -ne 0) {\n')
    f.write('        Write-Host "⚠️ Error on $cat, continuing..." -ForegroundColor Yellow\n')
    f.write('    }\n')
    f.write('}\n')
    f.write('Write-Host "`n✅ All paid categories done!" -ForegroundColor Green\n')

print(f"\n{'='*70}")
print(f"  📝 BATCH SCRIPTS GENERATED")
print(f"{'='*70}")
print(f"  scrape_all_free.ps1  — {len(free_slugs)} categories ({data['summary']['free_posts']:,} posts)")
print(f"  scrape_all_paid.ps1  — {len(paid_slugs)} categories ({data['summary']['paid_posts']:,} posts)")
print(f"\n  Run: .\\scrape_all_free.ps1")
print(f"  Run: .\\scrape_all_paid.ps1")
