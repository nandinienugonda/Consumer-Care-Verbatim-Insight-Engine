# ADR-0009: Cross-encoder reranking is required, with a no-op fallback

## Status

Accepted (2026-09-28). Promotes reranking from SHOULD to MUST in
`docs/project-architecture-proposal.md` Section 18.

## Context

The requirements include reranking in the hybrid retrieval pipeline.

## Decision

After Reciprocal Rank Fusion, up to `RERANK_CANDIDATES` items are reranked by the `Reranker` port
(cross-encoder adapter; model name in config only). On timeout or error the RRF order is kept and
the response is marked `degraded: [reranker]`. The keyword retriever starts as Postgres full-text
search; a true-BM25 adapter is added only if the retrieval ablation shows a gap.

## Consequences

- Retrieval evaluation reports an ablation with and without reranking.
- Rerank latency counts against the retrieval latency budget.
