import json
import os
from pathlib import Path

# Paths
stats_file = Path('scripts/db/stats_data.json')
artifact_dir = Path(r'C:\Users\xpeze\.gemini\antigravity-ide\brain\db53fe64-ed77-4f4e-aa0f-9d9d3bbb574f')

if not stats_file.exists():
    print(f"Stats data file not found at {stats_file}")
    exit(1)

with open(stats_file, 'r') as f:
    stats = json.load(f)

free_data = stats["is_paid = 0"]
paid_data = stats["is_paid = 1"]

# Colors for the graphs
bg_color = "#0B0F19"       # Deep obsidian navy
card_bg = "#111827"        # Dark slate
border_color = "#1F2937"   # Gray-800
text_main = "#F3F4F6"      # Gray-100
text_muted = "#9CA3AF"     # Gray-400

free_color = "#3B82F6"     # Bright Blue
free_grad = "url(#freeGrad)"
paid_color = "#EC4899"     # Rose Pink
paid_grad = "url(#paidGrad)"

# Ensure artifact directory exists
os.makedirs(artifact_dir, exist_ok=True)

# -------------------------------------------------------------
# 1. Circular Progress Rings for Scraped Coverage (overview.svg)
# -------------------------------------------------------------
def generate_overview_svg():
    width, height = 700, 300
    
    # Coverage calculation
    free_pct = free_data["scraped"] / max(free_data["available"], 1) * 100
    paid_pct = paid_data["scraped"] / max(paid_data["available"], 1) * 100
    
    # SVG circle math (r=60, circumference = 2 * pi * 60 = 376.99)
    r = 60
    c = 2 * 3.14159 * r
    
    free_offset = c - (free_pct / 100) * c
    paid_offset = c - (paid_pct / 100) * c
    
    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Definitions for Gradients -->
  <defs>
    <linearGradient id="freeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3B82F6" />
      <stop offset="100%" stop-color="#60A5FA" />
    </linearGradient>
    <linearGradient id="paidGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#EC4899" />
      <stop offset="100%" stop-color="#F43F5E" />
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>

  <!-- Background Card -->
  <rect width="{width}" height="{height}" rx="16" fill="{card_bg}" stroke="{border_color}" stroke-width="2"/>
  
  <text x="30" y="45" font-family="system-ui, sans-serif" font-size="20" font-weight="bold" fill="{text_main}">Scrape Coverage Overview</text>
  <text x="30" y="68" font-family="system-ui, sans-serif" font-size="14" fill="{text_muted}">Total scraped items compared to total available on website</text>

  <!-- Left Ring: Free Tier -->
  <g transform="translate(180, 180)">
    <!-- Base track -->
    <circle r="{r}" stroke="#1F2937" stroke-width="12" fill="none" />
    <!-- Progress track -->
    <circle r="{r}" stroke="{free_color}" stroke-dasharray="{c}" stroke-dashoffset="{free_offset}" stroke-width="12" stroke-linecap="round" fill="none" transform="rotate(-90)" />
    <!-- Inner labels -->
    <text text-anchor="middle" y="5" font-family="system-ui, sans-serif" font-size="24" font-weight="bold" fill="{text_main}">{free_pct:.1f}%</text>
    <text text-anchor="middle" y="160" font-family="system-ui, sans-serif" font-size="18" font-weight="bold" fill="{free_color}">FREE TIER</text>
    <text text-anchor="middle" y="180" font-family="system-ui, sans-serif" font-size="12" fill="{text_muted}">{free_data['scraped']:,} / {free_data['available']:,}</text>
  </g>

  <!-- Right Ring: Paid Tier -->
  <g transform="translate(520, 180)">
    <!-- Base track -->
    <circle r="{r}" stroke="#1F2937" stroke-width="12" fill="none" />
    <!-- Progress track -->
    <circle r="{r}" stroke="{paid_color}" stroke-dasharray="{c}" stroke-dashoffset="{paid_offset}" stroke-width="12" stroke-linecap="round" fill="none" transform="rotate(-90)" />
    <!-- Inner labels -->
    <text text-anchor="middle" y="5" font-family="system-ui, sans-serif" font-size="24" font-weight="bold" fill="{text_main}">{paid_pct:.1f}%</text>
    <text text-anchor="middle" y="160" font-family="system-ui, sans-serif" font-size="18" font-weight="bold" fill="{paid_color}">PAID TIER</text>
    <text text-anchor="middle" y="180" font-family="system-ui, sans-serif" font-size="12" fill="{text_muted}">{paid_data['scraped']:,} / {paid_data['available']:,}</text>
  </g>
</svg>
"""
    with open(artifact_dir / "overview_chart.svg", "w") as f:
        f.write(svg)
    print("Saved overview_chart.svg")

# -------------------------------------------------------------
# 2. Grouped Feature Enrichment Breakdown (enrichment.svg)
# -------------------------------------------------------------
def generate_enrichment_svg():
    width, height = 750, 430
    
    # Features to map
    features = [
        ("GDrive Link", "gdrive"),
        ("Mirror Link", "mirror"),
        ("Image Preview", "image"),
        ("File Size Info", "size_info"),
        ("Auto Tags", "tags"),
        ("Fully Enriched", "fully_enriched")
    ]
    
    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="freeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#2563EB" />
      <stop offset="100%" stop-color="#60A5FA" />
    </linearGradient>
    <linearGradient id="paidGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#DB2777" />
      <stop offset="100%" stop-color="#F43F5E" />
    </linearGradient>
  </defs>

  <!-- Background Card -->
  <rect width="{width}" height="{height}" rx="16" fill="{card_bg}" stroke="{border_color}" stroke-width="2"/>
  
  <text x="30" y="45" font-family="system-ui, sans-serif" font-size="20" font-weight="bold" fill="{text_main}">Feature Enrichment Breakdown (%)</text>
  <text x="30" y="68" font-family="system-ui, sans-serif" font-size="14" fill="{text_muted}">Percentage of scraped items containing specific data dimensions</text>
  
  <!-- Legend -->
  <g transform="translate(520, 40)">
    <rect x="0" y="0" width="14" height="14" rx="3" fill="#2563EB" />
    <text x="20" y="12" font-family="system-ui, sans-serif" font-size="12" fill="{text_main}">Free Tier</text>
    
    <rect x="100" y="0" width="14" height="14" rx="3" fill="#DB2777" />
    <text x="120" y="12" font-family="system-ui, sans-serif" font-size="12" fill="{text_main}">Paid Tier</text>
  </g>
"""
    
    start_y = 110
    row_height = 50
    bar_max_width = 450
    
    for idx, (label, key) in enumerate(features):
        y_pos = start_y + (idx * row_height)
        
        # Calculate percentages
        free_pct = free_data[key] / max(free_data["scraped"], 1) * 100
        paid_pct = paid_data[key] / max(paid_data["scraped"], 1) * 100
        
        free_width = (free_pct / 100) * bar_max_width
        paid_width = (paid_pct / 100) * bar_max_width
        
        # Feature label
        svg += f"""
  <text x="30" y="{y_pos + 22}" font-family="system-ui, sans-serif" font-size="13" font-weight="600" fill="{text_main}">{label}</text>
  
  <!-- Free Tier Bar Background -->
  <rect x="160" y="{y_pos}" width="{bar_max_width}" height="10" rx="3" fill="#1F2937" />
  <!-- Free Tier Bar Fill -->
  <rect x="160" y="{y_pos}" width="{max(free_width, 1)}" height="10" rx="3" fill="url(#freeGrad)" />
  <text x="{160 + max(free_width, 1) + 8}" y="{y_pos + 9}" font-family="system-ui, sans-serif" font-size="11" font-weight="bold" fill="{free_color}">{free_pct:.1f}%</text>

  <!-- Paid Tier Bar Background -->
  <rect x="160" y="{y_pos + 16}" width="{bar_max_width}" height="10" rx="3" fill="#1F2937" />
  <!-- Paid Tier Bar Fill -->
  <rect x="160" y="{y_pos + 16}" width="{max(paid_width, 1)}" height="10" rx="3" fill="url(#paidGrad)" />
  <text x="{160 + max(paid_width, 1) + 8}" y="{y_pos + 25}" font-family="system-ui, sans-serif" font-size="11" font-weight="bold" fill="{paid_color}">{paid_pct:.1f}%</text>
"""

    svg += "\n</svg>"
    
    with open(artifact_dir / "enrichment_chart.svg", "w") as f:
        f.write(svg)
    print("Saved enrichment_chart.svg")

if __name__ == "__main__":
    generate_overview_svg()
    generate_enrichment_svg()
