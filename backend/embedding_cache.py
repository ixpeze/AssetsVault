"""
Embedding Cache
===============
Loads all item embeddings into a pre-normalized numpy float32 matrix at
startup. Cosine similarity then reduces to a single matrix-vector multiply
(BLAS-backed via numpy), avoiding per-request full table scans and JSON
parsing overhead.

Format on disk: float32 little-endian BLOB (768 × 4 = 3072 bytes per row).
Fallback: JSON text blob (legacy, transparently decoded then cached as float32).

Latency estimates (768-dim, CPU, AVX2 BLAS):
  10k  vectors → ~2ms
  50k  vectors → ~8ms
  200k vectors → ~30ms
  500k vectors → ~75ms

Thread Safety
=============
All mutable state is confined to the `_state` dict.  A single `threading.RLock`
guards every read and write to `_state`.  `invalidate()` and `_ensure_loaded()`
both acquire the same lock, eliminating the write-read race that existed when
bare `global` assignments were used.
"""

import struct
import threading
import json

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

# Single mutable container + a single reentrant lock guard all state.
# Using a dict container avoids rebinding-under-lock bugs that raw globals have.
_lock  = threading.RLock()
_state = {"ids": None, "matrix": None}   # None == not loaded yet


# ---------------------------------------------------------------------------
# Binary encoding helpers (float32 little-endian)
# ---------------------------------------------------------------------------

def encode_embedding(vec) -> bytes:
    """Encode a list/array of floats as float32 LE bytes."""
    n = len(vec)
    return struct.pack(f'<{n}f', *vec)


def decode_embedding(blob) -> list:
    """Decode float32 LE bytes or JSON bytes to a Python list of floats."""
    if isinstance(blob, (bytes, bytearray)):
        if blob[:1] == b'[':
            # Legacy JSON blob
            return json.loads(blob.decode('utf-8', errors='replace'))
        n = len(blob) // 4
        return list(struct.unpack(f'<{n}f', blob[:n * 4]))
    if isinstance(blob, str):
        return json.loads(blob)
    return []


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def _load_locked(conn) -> None:
    """Read all embeddings from DB and build the normalised matrix.

    Must be called while holding `_lock`.
    """
    if not _NUMPY:
        _state["ids"]    = []
        _state["matrix"] = None
        return

    rows = conn.execute(
        "SELECT item_id, embedding FROM item_embeddings WHERE embedding IS NOT NULL"
    ).fetchall()

    if not rows:
        _state["ids"]    = np.array([], dtype=np.int64)
        _state["matrix"] = np.zeros((0, 1), dtype=np.float32)
        return

    ids  = []
    vecs = []
    dim  = None

    for row in rows:
        blob = row["embedding"]
        try:
            vec = decode_embedding(blob)
        except Exception:
            continue
        if not vec:
            continue
        if dim is None:
            dim = len(vec)
        if len(vec) != dim:
            continue
        ids.append(row["item_id"])
        vecs.append(vec)

    if not vecs:
        _state["ids"]    = np.array([], dtype=np.int64)
        _state["matrix"] = np.zeros((0, 1), dtype=np.float32)
        return

    mat   = np.array(vecs, dtype=np.float32)         # (N, D)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat  /= norms                                      # unit-normalise rows

    _state["ids"]    = np.array(ids, dtype=np.int64)
    _state["matrix"] = mat


def _ensure_loaded(conn) -> None:
    """Load the matrix if it has not been loaded yet (lazy, thread-safe)."""
    with _lock:
        if _state["ids"] is None:
            _load_locked(conn)


def invalidate() -> None:
    """Drop the cache so it is rebuilt on the next query (call after writes)."""
    with _lock:
        _state["ids"]    = None
        _state["matrix"] = None


# ---------------------------------------------------------------------------
# Query interface
# ---------------------------------------------------------------------------

def query(conn, query_vec, top_k: int = 50, threshold: float = 0.3) -> list:
    """
    Return [(item_id, score), ...] sorted by descending cosine similarity.

    Uses pre-normalised matrix: cosine sim = dot(q_unit, row).
    Falls back to pure-Python if numpy is unavailable (slow at scale).
    """
    _ensure_loaded(conn)

    with _lock:
        ids    = _state["ids"]
        matrix = _state["matrix"]

    if not _NUMPY or matrix is None or len(ids) == 0:
        return _query_pure_python(conn, query_vec, top_k, threshold)

    q    = np.array(query_vec, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    if norm == 0:
        return []
    q /= norm

    scores = matrix @ q    # (N,) — BLAS matrix-vector multiply

    n = len(ids)
    if top_k >= n:
        top_idx = np.argsort(scores)[::-1]
    else:
        # argpartition is O(N) vs argsort O(N log N)
        top_idx = np.argpartition(scores, -top_k)[-top_k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

    return [
        (int(ids[i]), float(scores[i]))
        for i in top_idx
        if scores[i] >= threshold
    ]


def query_for_item(conn, item_id: int, top_k: int = 50, threshold: float = 0.3) -> list:
    """
    Similarity search starting from a stored item's embedding.
    Excludes the source item from results.
    """
    row = conn.execute(
        "SELECT embedding FROM item_embeddings WHERE item_id = ?", (item_id,)
    ).fetchone()
    if not row:
        return []

    source_vec = decode_embedding(row["embedding"])
    if not source_vec:
        return []

    results = query(conn, source_vec, top_k=top_k + 1, threshold=threshold)
    return [(iid, sc) for iid, sc in results if iid != item_id][:top_k]


def _query_pure_python(conn, query_vec, top_k, threshold):
    """Slow fallback when numpy is not installed."""
    rows = conn.execute(
        "SELECT item_id, embedding FROM item_embeddings WHERE embedding IS NOT NULL"
    ).fetchall()
    scored  = []
    norm_q  = sum(x * x for x in query_vec) ** 0.5
    if norm_q == 0:
        return []
    for row in rows:
        try:
            vec    = decode_embedding(row["embedding"])
            dot    = sum(a * b for a, b in zip(query_vec, vec))
            norm_v = sum(x * x for x in vec) ** 0.5
            sim    = dot / (norm_q * norm_v) if norm_v else 0.0
            if sim >= threshold:
                scored.append((row["item_id"], sim))
        except Exception:
            pass
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
