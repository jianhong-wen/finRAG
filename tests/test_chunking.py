"""Tests for page chunking. A word counter stands in for the tokenizer."""

import pytest

from finrag.chunking import chunk_page


def words(text: str) -> int:
    return len(text.split())


def test_short_page_is_one_chunk_with_normalized_lines():
    text = "Revenue   increased\n\n  Costs fell  \n"
    assert chunk_page(text, "ctx", words, max_tokens=20, overlap_tokens=2) == [
        "Revenue increased\nCosts fell"
    ]


def test_empty_page_gives_no_chunks():
    assert chunk_page(" \n\n", "ctx", words, max_tokens=20, overlap_tokens=2) == []


def test_long_page_splits_between_lines_within_budget():
    lines = [f"row {i} value {i}" for i in range(30)]  # 4 words each
    chunks = chunk_page("\n".join(lines), "a b", words, max_tokens=22, overlap_tokens=4)
    assert len(chunks) > 1
    assert all(words(c) + words("a b") <= 22 for c in chunks)
    for chunk in chunks:
        assert all(line in lines for line in chunk.split("\n"))  # no line was cut


def test_consecutive_chunks_share_overlap_lines():
    lines = [f"row {i} value {i}" for i in range(12)]
    first, second, *_ = chunk_page("\n".join(lines), "", words, max_tokens=16, overlap_tokens=4)
    assert first.split("\n")[-1] == second.split("\n")[0]


def test_every_line_appears_in_some_chunk():
    lines = [f"row {i} value {i}" for i in range(40)]
    chunks = chunk_page("\n".join(lines), "", words, max_tokens=18, overlap_tokens=4)
    kept = {line for chunk in chunks for line in chunk.split("\n")}
    assert kept == set(lines)


def test_line_longer_than_budget_is_split_into_words():
    line = " ".join(f"w{i}" for i in range(25))
    chunks = chunk_page(line, "", words, max_tokens=10, overlap_tokens=2)
    assert all(words(c) <= 10 for c in chunks)
    assert " ".join(chunks).split() == line.split()


def test_context_that_leaves_no_room_is_rejected():
    with pytest.raises(ValueError, match="Context uses"):
        chunk_page("text", "one two three four five", words, max_tokens=6, overlap_tokens=2)
