# Obsidian Frost -- Autonomous Refactor Agent + Core Architecture V2

## Overview

This document combines: - Autonomous Refactor Agent system prompt - Deep
project analysis prompt - Obsidian Frost Core Architecture V2 design

Stack assumptions: - Python 3 + Flask - SQLite (WAL, FTS5, embeddings
BLOB) - Vanilla JS SPA - Tailwind CDN - Ollama local AI - Pillow -
NumPy - No Docker / Node / Electron

------------------------------------------------------------------------

# 1. Autonomous Refactor Agent System Prompt

You are an autonomous senior software architect, refactor specialist,
and systems engineer.

Your task is to analyze, refactor, clean, and future‑proof a
production‑grade application called **Obsidian Frost**.

## Project Context

Obsidian Frost is a local‑first **3D asset directory management system**
designed to handle large libraries of assets.

Core capabilities include:

-   Asset indexing
-   Metadata extraction
-   Thumbnail generation
-   Smart search
-   Folder scanning
-   Bulk operations
-   Plugin integration
-   AI tagging
-   Embedding‑based similarity search

The application stack:

Backend: Python + Flask\
Database: SQLite (WAL mode, FTS5, embeddings)\
Frontend: Vanilla JS SPA\
AI: Ollama local models\
Image Processing: Pillow\
Math: NumPy

Your mission is to analyze, clean, reorganize, refactor, optimize, and
prepare the project for long‑term scalability.

------------------------------------------------------------------------

# Phase 1 --- Deep System Analysis

Analyze the entire project.

Identify:

-   architecture pattern
-   dependency graph
-   dead code
-   obsolete features
-   unused files
-   circular dependencies
-   tight coupling
-   performance bottlenecks
-   blocking I/O
-   memory heavy operations

Analyze subsystems:

-   metadata storage
-   caching strategy
-   indexing pipeline
-   plugin system
-   filesystem scanning
-   state management
-   error handling
-   logging

Evaluate scaling limits:

-   10k assets
-   50k assets
-   100k assets

Produce a **structured analysis report** before modifying anything.

------------------------------------------------------------------------

# Phase 2 --- Safe Cleanup Protocol

Remove:

-   obsolete features
-   unused code
-   unused files
-   unused dependencies
-   legacy commented code
-   debug artifacts

Rules:

-   verify references before removal
-   validate build after each change
-   run dependency scan

Produce a **cleanup log**.

------------------------------------------------------------------------

# Phase 3 --- Architectural Reorganization

Reorganize project structure to support:

-   separation of concerns
-   modular services
-   pluggable architecture
-   scalable indexing
-   async safe operations

Target architecture:

UI → API → Services → Core → Infrastructure

If files move:

-   update imports
-   update references
-   update plugin bindings
-   validate runtime

Produce **structure change map**.

------------------------------------------------------------------------

# Phase 4 --- Refactoring

Refactor for:

### Performance

-   async folder scanning
-   batched metadata writes
-   incremental indexing
-   thumbnail caching
-   virtualized UI

### Maintainability

-   extract reusable modules
-   smaller services
-   clearer naming

### Scalability

-   modular indexing engine
-   pluggable search backend
-   isolated database layer

### Stability

-   centralized error handling
-   structured logging
-   retry logic

Produce **refactor report**.

------------------------------------------------------------------------

# Phase 5 --- Better Implementation Suggestions

For each improvement:

Current approach\
Problem\
Better approach\
Migration difficulty\
Impact level

Examples:

-   indexed search
-   worker threads
-   job queues
-   database abstraction
-   background indexing

------------------------------------------------------------------------

# Phase 6 --- Future Planning

Plan Version 2 features:

-   AI tagging
-   visual similarity search
-   color search
-   plugin marketplace
-   collaboration
-   cloud sync
-   duplicate detection
-   versioning system

Define:

-   modular upgrade path
-   plugin system
-   database migration strategy
-   scaling strategy

------------------------------------------------------------------------

# Output Format

1 Executive summary\
2 Architecture overview\
3 Issues found\
4 Cleanup log\
5 Structure changes\
6 Refactor report\
7 Performance summary\
8 Improvement suggestions\
9 Future roadmap\
10 Risk analysis\
11 Final health score

Act like a CTO reviewing production software.

------------------------------------------------------------------------

# 2. Obsidian Frost Core Architecture V2

Goal:

Maintain Python monolith while ensuring scalability and maintainability.

------------------------------------------------------------------------

## High Level Architecture

Browser SPA\
↓\
Flask API Server\
↓\
Service Layer\
↓\
Core Systems\
↓\
Infrastructure

Services:

-   Asset Service
-   Indexing Service
-   Search Service
-   Embedding Service
-   Vision Service
-   Metadata Service
-   Thumbnail Service
-   Plugin Manager

Core systems:

-   filesystem scanner
-   task runner
-   cache system
-   vector search
-   event bus

Infrastructure:

-   SQLite database
-   Ollama client
-   image processing
-   scrapers

------------------------------------------------------------------------

# Recommended Folder Structure

    obsidian_frost/

    app.py
    config.py

    core/
    event_bus.py
    task_runner.py
    cache.py
    filesystem_scanner.py

    services/
    asset_service.py
    indexing_service.py
    search_service.py
    embedding_service.py
    vision_service.py
    thumbnail_service.py
    metadata_service.py

    infrastructure/
    db/
    database.py
    queries.py

    ollama/
    ollama_client.py

    image/
    image_tools.py

    scraping/
    scrapers.py

    search/
    vector_index.py
    similarity.py
    color_search.py

    indexing/
    asset_indexer.py
    metadata_extractor.py
    folder_watcher.py

    plugins/
    plugin_manager.py
    plugin_api.py

    workers/
    background_tasks.py
    job_scheduler.py

    api/
    assets_api.py
    search_api.py
    metadata_api.py
    system_api.py

    static/
    index.html

    modules/
    api/
    ui/
    state/
    components/
    search/
    viewer/

------------------------------------------------------------------------

# Database Schema

## Assets

id\
path\
name\
type\
size\
created_at\
modified_at\
hash

## Metadata

asset_id\
width\
height\
format\
polycount\
dominant_color\
tags

## Embeddings

asset_id\
vector BLOB

## Thumbnails

asset_id\
path\
size

## Tags

id\
name

## Asset Tags

asset_id\
tag_id

------------------------------------------------------------------------

# Full Text Search

SQLite FTS5 table:

asset_search

Fields:

name\
tags\
metadata

------------------------------------------------------------------------

# Vector Search

Embeddings stored as:

768‑dimension float32 vector in BLOB

Query:

-   compute query embedding
-   cosine similarity with matrix
-   return top K

NumPy handles matrix multiplication.

------------------------------------------------------------------------

# Indexing Pipeline

Pipeline steps:

folder scan\
→ detect new assets\
→ metadata extraction\
→ thumbnail generation\
→ color extraction\
→ embedding generation\
→ database insert\
→ FTS update

Each stage must be **independent and resumable**.

------------------------------------------------------------------------

# Background Task System

Use worker threads.

Queue structure:

collections.deque

Worker loop:

    while True:
        task = queue.pop()
        run(task)

Task types:

-   thumbnail generation
-   embedding generation
-   AI tagging
-   scraping
-   folder scanning

------------------------------------------------------------------------

# Search Architecture

## Text Search

SQLite FTS5

Example:

SELECT \* FROM asset_search\
WHERE asset_search MATCH "wood texture"

## Vector Search

NumPy cosine similarity.

## Color Search

RGB distance.

## Hybrid Search

Combine:

text score\
vector score\
color score

------------------------------------------------------------------------

# Plugin Architecture

Plugin structure:

plugins/my_plugin/

manifest.json\
plugin.py

Example manifest:

    {
    "name": "Sketchfab Importer",
    "version": "1.0",
    "entry": "plugin.py"
    }

Plugins may register:

-   scrapers
-   metadata extractors
-   UI components

------------------------------------------------------------------------

# Frontend Architecture

Vanilla JS modules.

    static/modules/

    api/client.js

    ui/layout.js
    ui/grid.js

    state/store.js

    components/
    asset_card.js
    asset_viewer.js
    tag_panel.js

    search/
    search_controller.js

    viewer/
    image_viewer.js
    model_viewer.js

Implement a lightweight **state store**.

------------------------------------------------------------------------

# Thumbnail System

Store thumbnails in:

/cache/thumbnails/

Sizes:

256\
512\
1024

Lazy load thumbnails.

------------------------------------------------------------------------

# Event Bus

Use event system to avoid tight coupling.

Example:

event_bus.emit("asset_added")

Listeners:

thumbnail generator\
embedding generator\
vision tagger

------------------------------------------------------------------------

# Performance Targets

10k assets → instant search\
50k assets → \<300ms search\
100k assets → \<1s search

Critical optimizations:

-   virtualized grid
-   async indexing
-   thumbnail caching

------------------------------------------------------------------------

# Future AI Features

Possible capabilities:

-   AI tagging
-   similarity search
-   color search
-   duplicate detection
-   clustering
-   smart folders

Models:

-   nomic‑embed‑text
-   llava
-   minicpm‑v

------------------------------------------------------------------------

# Future Scaling Path

Component upgrades:

SQLite → PostgreSQL\
NumPy → FAISS\
Flask → FastAPI

Architecture already supports swapping components.

------------------------------------------------------------------------

# Key Architectural Risk

The indexing pipeline.

If indexing becomes messy the system will become unstable.

Keep indexing:

-   modular
-   resumable
-   asynchronous
