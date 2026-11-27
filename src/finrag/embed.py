"""Text embeddings.

Default backend: fastembed with BAAI/bge-small-en-v1.5 (384 dimensions, runs locally).
The "hash" backend is a simple word-hashing function for offline tests only.
Its retrieval quality is not meaningful.
"""

import hashlib
import re

import numpy as np

from .config import EMBED_BACKEND, EMBED_DIM

_model = None


def _fastembed_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model


def _hash_vector(text: str) -> np.ndarray:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.blake2b(token.encode(), digest_size=16).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0 if (h >> 64) & 1 else -1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


def embed_documents(texts: list[str]) -> list[np.ndarray]:
    if EMBED_BACKEND == "hash":
        return [_hash_vector(t) for t in texts]
    return [np.asarray(v, dtype=np.float32) for v in _fastembed_model().embed(texts)]


def embed_query(text: str) -> np.ndarray:
    if EMBED_BACKEND == "hash":
        return _hash_vector(text)
    return np.asarray(next(iter(_fastembed_model().query_embed(text))), dtype=np.float32)
