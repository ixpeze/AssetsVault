# Design Document: Parallel Browser-Based Paid Link Recapturer

This document details the architecture, design choices, concurrency control, and error handling for the parallelized Google Drive link extraction tool.

## 1. Understanding Summary
*   **Goal**: Accelerate GDrive link extraction for ~10,000 Paid tier items missing download links.
*   **Approach**: A single Playwright browser instance running multiple isolated async contexts (workers) in headless mode.
*   **Target Performance**: Concurrency of 5 to 10 workers, reducing execution time from ~30 hours down to ~3-5 hours.

## 2. Assumptions
*   A single authenticated session (`hello@auleek.com`) can be shared across 10 concurrent browser contexts navigating different pages on 3dskyfree.com.
*   The system has sufficient resources (CPU/RAM) to run a single Chromium process with 10 concurrent tabs/contexts.
*   Staggering startup and requests will mitigate Cloudflare Turnstile detection.

## 3. Decision Log

| Decision | Alternatives Considered | Rationale for Selection |
| :--- | :--- | :--- |
| **Single Browser + Multi-Context Async Workers** | Multithreaded Browser Pool, Range-Based Subprocesses | Extremely lightweight (1.5GB RAM vs 5GB+). Session sharing is native and doesn't require duplicate profile folders. |
| **`asyncio.Lock` for DB writes** | Direct concurrent SQLite writes in WAL mode | Prevents `database is locked` exceptions entirely by serializing DB transactions while allowing parallel page navigation. |
| **Staggered Worker Launch** | Simultaneous worker startup | Spacing out context launch by 2 seconds prevents initial connection spikes that trigger Cloudflare DDOS protections. |
| **Auto-Recovery Context Reset** | Total pause, immediate skip without restart | Resetting the browser context after a cooldown clears flags/cookies and restarts the session cleanly. |

## 4. Final Design Specification

### Orchestrator Lifecycle
1.  Initialize a single Chromium instance:
    ```python
    browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ```
2.  Perform a serialized login on page 0 with `wordpress_test_cookie` injected, and save storage state:
    ```python
    await browser_context.storage_state(path="data/auth_state.json")
    ```
3.  Query the target items from the SQLite database.
4.  Populate an `asyncio.Queue` and spawn $N$ workers.
5.  Wait for the queue to empty, then close the browser.

### Worker Execution loop
```python
async def worker(worker_id, queue, browser, db_write_lock, delay):
    # Staggered startup
    await asyncio.sleep(worker_id * 2.0)
    
    context = await browser.new_context(storage_state="data/auth_state.json")
    page = await context.new_page()
    
    while not queue.empty():
        item = await queue.get()
        try:
            await page.goto(item['post_url'])
            # Extract links and click Turnstile if present...
            gdrive, mirror = await extract_links(page)
            
            if gdrive or mirror:
                # Write to DB safely using the lock
                async with db_write_lock:
                    update_db(item['id'], gdrive, mirror)
            else:
                # Skip and restart context on block
                await context.close()
                await asyncio.sleep(30.0)
                context = await browser.new_context(storage_state="data/auth_state.json")
                page = await context.new_page()
        except Exception:
            # Handle navigation errors...
            pass
        finally:
            queue.task_done()
            await asyncio.sleep(delay)
            
    await context.close()
```
