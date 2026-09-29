# ADR-0005: Four-class query routing alongside retrieval strategies

## Status

Accepted (2026-09-28).

## Context

The requirements classify each query as KNOWLEDGE, REAL_TIME_DATA, TRANSACTIONAL/API or HYBRID.
The existing plan routes by retrieval method (graph, SQL, vector, hybrid). These are two different
axes: where the data comes from, and how CCVIE's own knowledge is retrieved.

## Decision

`contracts/router.py` gains `QueryClass`, `RetrievalStrategy`, `DecidedBy` and a
`RoutingDecision` model carrying `query_class`, `strategies`, `tools`, `confidence`, `decided_by`
and `reasons`.

- `HYBRID` is derived: it is assigned when the executed plan needs more than one data-source family.
- Deterministic rules decide first. The existing LLM Query Planner handles complex or
  low-confidence queries. No second LLM classifier is added.
- Planner failure falls back to KNOWLEDGE with vector + keyword retrieval, or a clarification when a
  transactional verb is present.
- The legacy `RouteDecision` enum stays until the frontend routing page is migrated (Phase 4), then
  it is removed.

## Consequences

- `data/golden/` router labels are rebuilt with `query_class` and `strategies`.
- Routing accuracy is reported per class and against an always-KNOWLEDGE baseline.
