"""Tests for the offline embedding backend. No database or network needed."""

import numpy as np

from finrag.config import EMBED_DIM
from finrag.embed import embed_documents, embed_query


def test_vectors_have_schema_dimension():
    vec = embed_documents(["Revenue increased."])[0]
    assert vec.shape == (EMBED_DIM,)


def test_vectors_are_normalized():
    vec = embed_query("supply chain risk")
    assert np.isclose(np.linalg.norm(vec), 1.0)


def test_same_text_gives_same_vector():
    a = embed_query("capital expenditures")
    b = embed_documents(["capital expenditures"])[0]
    assert np.allclose(a, b)


def test_empty_text_gives_zero_vector():
    assert not embed_query("").any()
