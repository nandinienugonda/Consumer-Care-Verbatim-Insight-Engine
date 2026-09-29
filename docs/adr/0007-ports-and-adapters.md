# ADR-0007: Ports-and-adapters backend layout

## Status

Accepted (2026-09-28). Amends the folder tree in `docs/project-architecture-proposal.md` Section 3.

## Context

The vector store, keyword index, embedding model, LLM, reranker, cache and queue must be replaceable
without changing application code. The FastAPI app also needs to be an entrypoint of its own, not a
file inside the Retrieval and Generation layer.

## Decision

- `ccvie/core/ports.py` defines `typing.Protocol` interfaces. Application code imports ports only.
- `ccvie/adapters/` holds implementations. `ccvie/bootstrap/container.py` is the only place that
  chooses an adapter, based on `config.py`.
- The FastAPI app moves from `ccvie.retrieval_gen.api` to `ccvie.api.app` (factory `create_app`,
  module-level `app`).
- The five layer packages (`data_foundation`, `router`, `retrieval_gen`, `evaluation`,
  `contracts`) stay.

## Consequences

- Start command becomes `uvicorn ccvie.api.app:app`.
- Every adapter must pass the shared contract test suite for its port.
