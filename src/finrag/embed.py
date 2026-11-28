"""Text embeddings.

Default backend: fastembed with BAAI/bge-small-en-v1.5 (384 dimensions, runs locally).
The "hash" backend is a simple word-hashing function for offline tests only.
Its retrieval quality is not meaningful.
"""

import hashlib
import math
import re
from typing import Any

import numpy as np
import numpy.typing as npt

from .config import EMBED_BACKEND, EMBED_DIM

Vector = npt.NDArray[np.float32]
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MODEL_MAX_TOKENS = 512
SPECIAL_TOKENS = 2  # [CLS] and [SEP]

_model: Any = None  # fastembed ships no type hints


def _fastembed_model() -> Any:
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(EMBED_MODEL)
    return _model


def _hash_vector(text: str) -> Vector:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.blake2b(token.encode(), digest_size=16).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0 if (h >> 64) & 1 else -1.0
    norm = np.linalg.norm(vec)
    return (vec / norm).astype(np.float32) if norm else vec


def embed_documents(texts: list[str]) -> list[Vector]:
    """Return one normalized EMBED_DIM vector per text, in input order."""
    if EMBED_BACKEND == "hash":
        return [_hash_vector(t) for t in texts]
    return [np.asarray(v, dtype=np.float32) for v in _fastembed_model().embed(texts)]


def embed_query(text: str) -> Vector:
    """Return the EMBED_DIM vector for a search query."""
    if EMBED_BACKEND == "hash":
        return _hash_vector(text)
    return np.asarray(next(iter(_fastembed_model().query_embed(text))), dtype=np.float32)


def estimate_tokens(text: str) -> int:
    """Estimate word-piece tokens without a tokenizer, erring on the high side.

    Each punctuation mark counts as one token and each run of letters or digits as one
    token per four characters, as a WordPiece tokenizer splits numbers like "(1,577)".
    """
    pieces = re.findall(r"[A-Za-z]+|\d+|[^\w\s]", text)
    return sum(math.ceil(len(p) / 4) if p.isalnum() else 1 for p in pieces)


def count_tokens(text: str) -> int:
    """Return the number of model tokens in text, without the two special tokens.

    The hash backend uses estimate_tokens. The fastembed count stops at the model limit
    (512 tokens) because its tokenizer truncates.
    """
    if EMBED_BACKEND == "hash":
        return estimate_tokens(text)
    return max(0, int(_fastembed_model().token_count(text)) - SPECIAL_TOKENS)
