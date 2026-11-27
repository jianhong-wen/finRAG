# ADR 0001: One PostgreSQL database with pgvector

Date: 2026-11-27. Status: accepted.

## Context
The system needs document chunks (text and vectors) and structured numbers (facts).
Answers often need both, linked to the same filing.

## Decision
Store both in one PostgreSQL database. Use pgvector for vectors and PostgreSQL full-text
search (`tsvector`) for keyword search. Host it on Neon (free plan) for the demo.

## Alternatives considered
- A separate vector database (for example Qdrant) plus PostgreSQL: two systems to keep in
  sync, and no SQL join between chunks and facts.
- SQLite with a local vector index: simpler locally, but further from a production setup.

## Consequences
- Chunks and facts join on `filing_id`; one audit trail and one access-control model.
- The Neon free plan limits storage to 1 GB per project, which limits the corpus size.
