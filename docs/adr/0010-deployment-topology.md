# ADR-0010: Independently scalable containers from one backend codebase

## Status

Accepted (2026-09-28). Extends `docs/project-architecture-proposal.md` Section 2; deployment stays
local Docker Compose.

## Context

Components must scale independently. Microservices per component would add release and dependency
overhead the project does not need.

## Decision

One backend image with several entrypoints (`api`, `ingest-worker`, `embed-worker`, `detector`,
`outbox-relay`), plus separate images for the frontend and the MCP servers. Model serving
(embedding, reranker, NLI) runs in-process by default and moves to its own container through the
`EMBEDDING_BACKEND=remote` adapter when needed. No Kubernetes or cloud infrastructure in this
repository.

## Consequences

- Stateless API: conversation state in Postgres, shared state in Redis.
- Compose services can be scaled with `docker compose up --scale`.
