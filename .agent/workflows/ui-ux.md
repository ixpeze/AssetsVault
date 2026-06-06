---
description: Apply UI/UX Pro Max design intelligence when building or reviewing any interface
---

> **🔗 Linked Skill:** This workflow is permanently coupled with `skills/ui-ux-pro-max/SKILL.md`.
> Invoking **either** this workflow **or** the skill activates **both**.
> Step 1 below is mandatory and non-skippable.

# UI/UX Pro Max Workflow

Use this workflow whenever designing, building, reviewing, or improving any user interface. It drives the BM25-powered design intelligence database to produce style, color, typography, and UX recommendations before implementation.

## Steps

1. **⚠️ MANDATORY — Read the skill** — Use `view_file` on `skills/ui-ux-pro-max/SKILL.md` and follow its instructions exactly. This step cannot be skipped.

2. **Analyze the request** — Extract from the user's message:
   - Product type (SaaS, e-commerce, portfolio, dashboard, landing page, etc.)
   - Style keywords (minimal, playful, professional, elegant, dark mode, etc.)
   - Industry (healthcare, fintech, gaming, education, etc.)
   - Tech stack (React, Vue, Next.js — or default to `html-tailwind`)

3. **Generate design system (REQUIRED)** — Always start with `--design-system`:
   ```bash
   python skills/ui-ux-pro-max/scripts/search.py "<product_type> <industry> <keywords>" --design-system [-p "Project Name"]
   ```

4. **Supplement with domain searches (as needed)** — Use targeted queries for more detail:
   ```bash
   python skills/ui-ux-pro-max/scripts/search.py "<keyword>" --domain <domain>
   ```
   Priority order: `ux` → `style` → `typography` → `color` → `landing` → `chart`

5. **Get stack guidelines** — Apply implementation-specific best practices:
   ```bash
   python skills/ui-ux-pro-max/scripts/search.py "<keyword>" --stack html-tailwind
   ```

6. **Implement the design** — Synthesize all search results and build the UI. Apply the pre-delivery checklist from the skill before finishing:
   - No emoji icons (SVG only)
   - `cursor-pointer` on all clickable elements
   - Smooth transitions (150–300ms)
   - Light mode contrast ≥ 4.5:1
   - Keyboard focus states visible
   - `prefers-reduced-motion` respected
   - Responsive at 375px, 768px, 1024px, 1440px

7. **Review before delivery** — Run through the full Pre-Delivery Checklist in `SKILL.md` before returning output to the user.
