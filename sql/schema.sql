-- Schema for the finance RAG project (PostgreSQL + pgvector).
-- Safe to run more than once.

create extension if not exists vector;

-- One row per source document (for example, one SEC filing).
create table if not exists filings (
  filing_id   text primary key,          -- for example an SEC accession number
  company     text not null,
  cik         text,
  form        text,                      -- 10-K, 10-Q, annual report, ...
  fiscal_year int,
  period_end  date,
  source_url  text,
  ingested_at timestamptz not null default now()
);
-- Added for idempotent loading (ADR 0007): a document is reloaded only when its file
-- or the processing pipeline changes.
alter table filings add column if not exists source_sha256 text;
alter table filings add column if not exists pipeline_version text;

-- Maps raw reporting tags (for example XBRL tags) to one normalized concept name.
create table if not exists concept_aliases (
  raw_tag text primary key,
  concept text not null
);

-- Structured numbers. "source" records where each number came from.
create table if not exists facts (
  fact_id      bigserial primary key,
  filing_id    text not null references filings(filing_id) on delete cascade,
  concept      text not null,            -- normalized, for example revenue
  raw_tag      text,                     -- original tag
  period_start date,
  period_end   date,
  value        numeric not null,
  unit         text,
  source       text not null check (source in ('xbrl', 'pdf_table')),
  page         int,
  confidence   real
);
create index if not exists facts_lookup on facts (concept, filing_id);

-- Text chunks from documents. The vector size (384) matches the
-- BAAI/bge-small-en-v1.5 embedding model. Change both together.
create table if not exists chunks (
  chunk_id  bigserial primary key,
  filing_id text not null references filings(filing_id) on delete cascade,
  page      int,
  section   text,
  text      text not null,
  context   text,                        -- short generated description of the chunk
  embedding vector(384),
  tsv       tsvector generated always as
            (to_tsvector('english', coalesce(context, '') || ' ' || text)) stored
);
create index if not exists chunks_tsv on chunks using gin (tsv);
-- HNSW (Hierarchical Navigable Small World) index for fast vector search.
create index if not exists chunks_embedding on chunks using hnsw (embedding vector_cosine_ops);

-- Audit trail: one row per tool call made by the agent.
create table if not exists audit_log (
  id             bigserial primary key,
  ts             timestamptz not null default now(),
  question       text,
  tool           text not null,
  input          jsonb,
  output_summary jsonb,
  latency_ms     int
);
