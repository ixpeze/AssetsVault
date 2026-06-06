---
name: automating-workflows
description: Automates workflows like batch scraping. Use when the user wants to generate scripts or run bulk operations.
---

# Automating Workflows

## When to use this skill
- When the user wants to "automate" or "batch" operations.
- When the user mentions `generate_batch_commands.py` or `.ps1` scripts.
- When the user wants to regenerate `scrape_all_free.ps1` or `scrape_all_paid.ps1`.

## Workflow
1. **Analyze Requirements**: Determine which workflow needs automation.
2. **Generate Scripts**: Run `python generate_batch_commands.py`.
3. **Execute**: Run the generated scripts.

## Instructions

### Generating Batch Scraping Scripts
Based on the `category_classification.json`, this script generates PowerShell scripts to scrape all categories in batches.
- **Input**: `category_classification.json` (Ensure `classify_categories.py` has run first).
- **Output**: `scrape_all_free.ps1`, `scrape_all_paid.ps1`.

```bash
python generate_batch_commands.py
```

### Running Batch Scripts
After generation, execute the scripts:
```powershell
.\scrape_all_free.ps1
```

## Resources
- [generate_batch_commands.py](file:///g:/AI/3DSkyFree/generate_batch_commands.py)
