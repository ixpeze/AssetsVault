---
name: managing-data
description: Managing the 3dskyfree.com database and content. Use when the user wants to process images, generate embeddings, or classify categories.
---

# Managing Data

## When to use this skill
- When the user wants to "process" or "enrich" the database.
- When the user mentions "colors", "embeddings", or "classification".
- When the user mentions `extract_colors.py`, `generate_embeddings.py`, or `classify_categories.py`.

## Workflow
1. **Understand Goal**: Determine if the user wants to classify free/paid, extract colors, or generate embeddings.
2. **Select Script**:
    - **Classification**: `python classify_categories.py`
    - **Color Extraction**: `python extract_colors.py`
    - **Embeddings**: `python generate_embeddings.py`
3. **Run Script**: Execute the script.
4. **Verify**: Check `3dskyfree.db` or `category_classification.json` for results.

## Instructions

### Classify Categories
Updates `category_classification.json` to distinguish Free vs Paid categories.
```bash
python classify_categories.py
```

### Extract Dominant Colors
Analyzes downloaded images to find dominant colors and stores them in `item_colors`.
- **Prerequisite**: Images must be downloaded first (use `scraping-content` skill).
```bash
# Process all untagged items
python extract_colors.py

# Process specific batch size
python extract_colors.py --batch-size 500

# Reset and re-process all
python extract_colors.py --reset
```

### Generate Semantic Embeddings
Uses Ollama to create vector embeddings for items, enabling semantic search.
- **Prerequisite**: [Ollama](https://ollama.com/) must be installed and running.
- **Model**: Requires `nomic-embed-text` model (`ollama pull nomic-embed-text`).
```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Generate embeddings for unindexed items
python generate_embeddings.py

# Reset and re-index all
python generate_embeddings.py --reset
```

## Resources
- [classify_categories.py](file:///g:/AI/3DSkyFree/classify_categories.py)
- [extract_colors.py](file:///g:/AI/3DSkyFree/extract_colors.py)
- [generate_embeddings.py](file:///g:/AI/3DSkyFree/generate_embeddings.py)
