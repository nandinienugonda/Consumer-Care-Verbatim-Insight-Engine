# ADR-0008: Redis for cache, job queue, rate limits and breaker state

## Status

Accepted (2026-09-28).

## Context

API replicas need shared state for caching, rate limiting and circuit breakers. Ingestion needs an
asynchronous job queue. The earlier plan preferred Postgres as the only store.

## Decision

Add Redis. It backs the `Cache` and `JobQueue` ports. The document embedding cache stays in
Postgres (`embedding_cache`) because it must be durable. An in-memory `Cache` adapter serves tests
and single-process development.

## Consequences

- One more service in Docker Compose and in production.
- A Postgres `SKIP LOCKED` queue adapter remains a valid fallback for minimal deployments.
