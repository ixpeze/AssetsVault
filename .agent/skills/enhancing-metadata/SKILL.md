---
name: enhancing-metadata
description: Uses AI to generate descriptive tags for 3D assets.
---

# Enhancing Metadata

## When to use this skill
- When the user wants to "tag" items or "generate tags".
- When the user mentions "AI", "Ollama", "LLaVA", or `ai_tagger.py`.
- When the user wants to improve searchability by adding visual descriptions.

## Workflow
1. **Check Prerequisites**: Ensure Ollama is running and the vision model (`minicpm-v` or `llava`) is pulled.
2. **Run Tagger**: Execute `ai_tagger.py`.
3. **Verify**: Check `tags` and `item_tags` tables in `3dskyfree.db`.

## Instructions

### Setup
1. Install [Ollama](https://ollama.com/).
2. Pull the default model:
   ```bash
   ollama pull minicpm-v
   ```

### Running the Tagger
The script analyzes local images and generates 5-8 descriptive tags.

```bash
# Process all untagged items
python ai_tagger.py

# specific batch size
python ai_tagger.py --batch-size 50

# Dry run (preview only)
python ai_tagger.py --dry-run
```

### Custom Model
You can use other vision models like `llava` or `llama3.2-vision`.
```bash
python ai_tagger.py --model llava
```

## Resources
- [ai_tagger.py](file:///g:/AI/3DSkyFree/ai_tagger.py)
