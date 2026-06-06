---
name: running-app
description: Running the 3D Sky Free web application. Use when the user wants to start the web server or view the gallery.
---

# Running App

## When to use this skill
- When the user wants to "start the app" or "view the gallery".
- When the user mentions `run.py` or `localhost:5000`.

## Workflow
1. **Check Dependencies**: Ensure `requirements.txt` is installed.
2. **Start Server**: Run `python run.py`.
3. **Access App**: Open browser at `http://localhost:5000`.

## Instructions

### Setup
Ensure all dependencies are installed active virtual environment (if used).
```bash
pip install -r requirements.txt
```

### Running the Server
Start the Flask development server.
```bash
python run.py
```
The app will be available at [http://localhost:5000](http://localhost:5000).

### Troubleshooting
- **Port in use**: If port 5000 is busy, modify `run.py` or kill the existing process.
- **Database missing**: Ensure `3dskyfree.db` exists (run scraper or copy backup).

## Resources
- [run.py](file:///g:/AI/3DSkyFree/run.py)
