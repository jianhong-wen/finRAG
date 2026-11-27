# ADR 0003: Fixed, parameterized SQL tools instead of model-written SQL

Date: 2026-11-27. Status: accepted.

## Context
The agent needs structured numbers. One option is to let the model write SQL.

## Decision
The model calls tools with fixed, parameterized SQL (`get_fact`). The model supplies only
parameter values. When `get_fact` finds nothing, it returns the concepts that exist.

## Alternatives considered
- Model-written SQL on a read-only view: more flexible, but harder to test and to audit,
  and errors are harder to detect.

## Consequences
- Queries are testable and safe from SQL injection.
- Questions that need new query shapes (for example comparing two years) need new tools.
  A restricted read-only SQL tool may be added later, behind its own ADR.
