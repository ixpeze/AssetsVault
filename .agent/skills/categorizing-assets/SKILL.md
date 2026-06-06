---
name: categorizing-assets
description: Smartly sort and organize 3D assets into logical hierarchies (categories > sub-categories) and clean up tags using a local LLM.
---

# Categorizing Assets

## When to use this skill
- When the user wants to "sort", "organize", or "clean up" categories or tags.
- When the list of categories is too flat or messy.
- When there are duplicate or synonymous tags (e.g., "sofa", "couches").

## Workflow
1. **Check Prerequisites**: Ensure [Ollama](https://ollama.com/) is running and you have a text model installed.
    - Recommended: `ollama pull llama3`
    - Alternative: `ollama pull mistral`
2. **Run Organizer**: Execute `organize_assets.py`.
3. **Verify**: Check `3dskyfree.db` for updated `parent_id` in categories or merged tags.

## Instructions

### Organize Categories
Uses an LLM to build a hierarchy from flat categories.
- Assigns valid `parent_id` to categories.
- Creates top-level categories if they don't exist (conceptually, or by adding them to the DB).

```bash
# Preview changes (dry-run)
python organize_assets.py categories --dry-run

# Apply changes
python organize_assets.py categories
```

### Organize Tags
identifies synonyms and merges them.
- Example: Merges "table lamp" and "table-lamp" into "table lamp".

```bash
# Preview changes
python organize_assets.py tags --dry-run

# Apply changes
python organize_assets.py tags
```

### Custom Model
Specify a different Ollama model.
```bash
python organize_assets.py categories --model llama3
```

## Resources
- [organize_assets.py](file:///g:/AI/3DSkyFree/organize_assets.py)
