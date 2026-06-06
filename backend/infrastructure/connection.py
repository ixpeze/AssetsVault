"""
infrastructure.connection — SQLite connection management.

Per-Request Connection Reuse
-----------------------------
`get_db()` uses `threading.local()` to return the same connection for the
entire lifetime of a request (one connection per thread).  This avoids the
overhead of open/PRAGMA/close on every route handler.

`close_db()` must be called at the end of each request to return the
connection (in Flask via `teardown_appcontext`).  The app factory wires
this up automatically via `app.teardown_appcontext(close_db)`.

Connection-level PRAGMAs are applied once when a new connection is first
opened for a thread.  Database-level PRAGMAs (journal_mode, mmap_size,
wal_autocheckpoint) are set once in `persistence.schema.init_schema()` at
startup and persist across connections.

Standalone Scripts
------------------
Root-level pipeline scripts that do NOT run inside Flask should call the
module-level `get_db()` directly — they get a fresh connection each call
(the thread-local is a process thread, so standalone processes have their
own local storage and see no Flask connections).
"""
import logging
import sqlite3
import threading
from ..constants import DB_PATH

log  = logging.getLogger(__name__)
_tls = threading.local()   # thread-local connection storage


def get_db() -> sqlite3.Connection:
    """Return the current thread's reusable SQLite connection.

    Opens and configures a new connection on first call per thread.
    Subsequent calls within the same thread (same request) return the
    cached connection without re-applying PRAGMAs.
    """
    conn = getattr(_tls, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            _tls.conn = None

    if not getattr(_tls, "conn", None):
        conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Connection-level PRAGMAs (applied once per connection)
        conn.execute("PRAGMA synchronous  = NORMAL")   # survives OS crash; ~1 ms writes
        conn.execute("PRAGMA cache_size   = -65536")   # 64 MB page cache (neg = KB)
        conn.execute("PRAGMA temp_store   = MEMORY")   # keep sort buffers in RAM
        conn.execute("PRAGMA busy_timeout = 5000")     # ms before SQLITE_BUSY
        _tls.conn = conn
        log.debug("[DB] Opened new SQLite connection for thread %s", threading.current_thread().name)
    return _tls.conn


def close_db(exc=None) -> None:
    """Close the current thread's connection.

    Called by Flask's teardown_appcontext at the end of each request.
    Also safe to call manually at the end of a script or test.

    Guard against ProgrammingError: Flask's teardown can fire after a
    streaming response has already consumed/closed the connection.
    """
    conn = getattr(_tls, "conn", None)
    if conn is None:
        return
    try:
        if exc:
            conn.rollback()
        else:
            conn.commit()
        conn.close()
        log.debug("[DB] Closed SQLite connection for thread %s", threading.current_thread().name)
    except Exception as e:  # noqa: BLE001
        # Connection was already closed (e.g. mid-streaming teardown).
        # Log at DEBUG so we don't spam the console, then discard.
        log.debug("[DB] close_db: connection already closed (%s)", e)
    finally:
        _tls.conn = None



def get_db_fresh() -> sqlite3.Connection:
    """
    Return a brand-new, uncached connection (bypasses thread-local pool).

    Use for long-running background scripts that must not share a connection
    with Flask request handlers, or when you need an independent transaction.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous  = NORMAL")
    conn.execute("PRAGMA cache_size   = -65536")
    conn.execute("PRAGMA temp_store   = MEMORY")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
