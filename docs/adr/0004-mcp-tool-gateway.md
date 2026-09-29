# ADR-0004: Adopt MCP behind an internal Tool Gateway

## Status

Accepted (2026-09-28). Supersedes the "Do not add MCP" warning in
`docs/project-architecture-proposal.md` Section 10 and moves "MCP wrapper" out of Section 18's
COULD/FUTURE tier.

## Context

The production requirements need live enterprise data (REAL_TIME_DATA queries) and state-changing
actions (TRANSACTIONAL queries) in addition to CCVIE's indexed knowledge. MCP is a standard
protocol for tool discovery, typed arguments and results. The earlier capstone plan excluded it to
protect a two-week scope.

## Decision

CCVIE calls enterprise tools only through `ccvie.tools.gateway`. The gateway reads a committed
registry (`backend/src/ccvie/tools/registry.yaml`) that owns tool descriptions, schemas, scopes,
roles, timeouts, cache TTLs and confirmation requirements. MCP (streamable HTTP) is the default
transport. Three synthetic MCP servers are implemented under `mcp-servers/`: `care-ops`,
`supply-chain`, `quality-cases`.

- Server-advertised tool descriptions are never shown to the LLM.
- Advertised input schemas are compared with the registry at startup; a mismatch disables the tool.
- The gateway injects `tenant_id` and principal from the verified request, never from LLM output.
- WRITE tools create a `PendingAction` and run only after explicit user confirmation.
- MCP servers re-check tenant and scope.

## Consequences

- One extra network hop per tool call and a protocol surface to secure.
- Any tool can be moved to a direct REST adapter behind the same gateway interface.
- The router, planner and evaluation must now cover tool selection and tool success rate.
