# ADR 0002: 384-dimension embeddings (BAAI/bge-small-en-v1.5)

Date: 2026-11-27. Status: accepted.

## Context
Each vector is stored in the database. Storage on the free plan is limited to 1 GB.

## Decision
Use BAAI/bge-small-en-v1.5 through fastembed. It produces 384-dimension vectors and runs
locally without an API key.

## Alternatives considered
- 1024-dimension models: about 4 KB per vector instead of about 1.5 KB.
- Hosted embedding APIs: cost per call, and a network dependency in tests.

## Consequences
- Lower storage use. Retrieval quality has not been measured yet; the FinanceBench
  evaluation will show whether a larger model is needed.
- Changing the model requires changing `vector(384)` and `EMBED_DIM` together and
  re-embedding all chunks.
