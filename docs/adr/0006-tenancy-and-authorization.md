# ADR-0006: Multi-tenant RBAC/ABAC with Postgres Row-Level Security

## Status

Accepted (2026-09-28).

## Context

Retrieval must be filtered by role, tenant and access metadata before any content reaches the LLM.
Authorization must never depend on the LLM. The existing plan had no tenancy or roles.

## Decision

- Identity comes only from a verified JWT (OIDC in production, a local HS256 dev issuer in
  development). The request body never carries identity.
- `ccvie.security.policy` turns a `Principal` into an immutable `AccessFilter`
  (tenant, regions, brands, max classification). Deny by default.
- Every retriever port takes `AccessFilter` as a required argument.
- Every tenant-owned table has `tenant_id` and an RLS policy keyed on the transaction-local setting
  `app.tenant_id`. Application roles do not have `BYPASSRLS`.
- Retrieved items are re-checked against the `AccessFilter` before context construction; a
  violation fails the request closed.
- Every cache key includes a hash of the `AccessFilter`.

## Consequences

- Each query transaction runs `set_config('app.tenant_id', …, true)` first.
- The synthetic dataset and all golden sets gain tenants, users and roles.
- A cross-tenant leak test is a hard CI gate (leak rate must be 0).
