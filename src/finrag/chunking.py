"""Split page text into chunks that fit the embedding model (ADR 0007).

Rules: a chunk never spans two pages; text is split between lines, so a table row stays
in one chunk; consecutive chunks of a page share a few trailing lines (overlap). Token
counts come from a counter passed in by the caller, so this module has no model or I/O.
"""

from collections.abc import Callable

MAX_TOKENS = 350  # per chunk including its context line; the model reads at most 512
OVERLAP_TOKENS = 50

TokenCounter = Callable[[str], int]


def _split_long_line(line: str, budget: int, count: TokenCounter) -> list[str]:
    """Split one line that exceeds the budget into word groups that fit."""
    pieces: list[str] = []
    current: list[str] = []
    for word in line.split():
        if current and count(" ".join([*current, word])) > budget:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _overlap(lines: list[str], sizes: list[int], overlap_tokens: int) -> int:
    """Return how many trailing lines fit into the overlap budget."""
    total = taken = 0
    for size in reversed(sizes):
        if total + size > overlap_tokens or taken == len(lines) - 1:
            break
        total += size
        taken += 1
    return taken


def chunk_page(
    text: str,
    context: str,
    count: TokenCounter,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[str]:
    """Split one page into chunk texts; each fits max_tokens together with context.

    Returns [] for a page without text. Raises ValueError if context alone leaves no
    room for text.
    """
    budget = max_tokens - count(context)
    if budget <= overlap_tokens:
        raise ValueError(f"Context uses {max_tokens - budget} of {max_tokens} tokens")
    lines: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line:
            lines.extend(_split_long_line(line, budget, count) if count(line) > budget else [line])
    chunks: list[str] = []
    current: list[str] = []
    sizes: list[int] = []
    for line in lines:
        size = count(line)
        if current and sum(sizes) + size > budget:
            chunks.append("\n".join(current))
            keep = _overlap(current, sizes, overlap_tokens)
            current, sizes = current[len(current) - keep :], sizes[len(sizes) - keep :]
            while current and sum(sizes) + size > budget:  # overlap must not overfill
                current, sizes = current[1:], sizes[1:]
        current.append(line)
        sizes.append(size)
    if current:
        chunks.append("\n".join(current))
    return chunks
