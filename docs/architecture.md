# CCVIE Production Architecture

Status: **APPROVED 2026-09-28.** Decisions recorded in `docs/adr/0004`–`0010`. Phase 1 (skeleton)
implemented and verified, including the Postgres RLS integration tests.

This is the system design for the production-oriented CCVIE build. It extends
`docs/project-architecture-proposal.md` (the capstone plan and repository rules). Where the two
disagree, Section 29 lists every conflict and the ADR each one needs before implementation starts.
Model names are deliberately absent from this document; every model is referenced by its
`config.py` key (Rule 3 in `CLAUDE.md`).

---

## 1. Context, goals, non-goals

### 1.1 Business problem

Consumer-care contacts carry the earliest signal of product, packaging and quality failures.
Monthly category reports aggregate those contacts into broad themes and hide localized, fast-growing
clusters. The synthetic dataset in this repository already contains one:

```
Category report:   "Hair Care packaging complaints up modestly month over month"
Underlying cell:   FreshGlow Shampoo  x  500ml New Bottle  x  South  x  Leakage
                   4-9 complaints/month from Feb 2026, near zero elsewhere for that pack
```

CCVIE must surface that cell early, answer questions about it in natural language, pull live
operational data and trigger follow-up actions through enterprise tools, and **attribute every
generated claim to the original customer contacts**.

### 1.2 Goals

| # | Goal | Measured by |
|---|------|-------------|
| G1 | Detect emerging pack/product/issue/region clusters before monthly reporting would | Lead time vs. monthly and weekly baselines (existing `evaluation/lead_time.py`) |
| G2 | Answer thematic and structured natural-language questions | Answer relevance, faithfulness, numeric correctness |
| G3 | Route each query to vector RAG, graph RAG, enterprise tools, or a combination | Routing accuracy, per-class precision/recall |
| G4 | Every claim carries a verifiable citation to a source contact, fact, or tool result | Citation correctness, groundedness |
| G5 | Users only ever see data they are authorized for, enforced outside the LLM | Cross-tenant/cross-scope leak tests: must be 0 |
| G6 | Components scale and fail independently | Load and failure-injection tests |
| G7 | Vector DB, embedding model, LLM, reranker are swappable by configuration | Adapter contract tests pass for each implementation |

### 1.3 Non-goals

- No real customer data or PII. All data is synthetic; the PII pipeline is still built and tested
  with synthetic PII so it is ready for real data.
- No dedicated graph database (existing rule, unchanged).
- No autonomous multi-agent loops. The orchestration graph is bounded and acyclic (existing rule,
  unchanged).
- No cloud-provider-specific infrastructure in this repository. The design is container-based and
  orchestrator-agnostic; local deployment is Docker Compose.
- No LLM-issued SQL, ever (existing Query Planner Safety Rule, unchanged).

### 1.4 Quality attribute targets

These are **design targets to be validated by load tests**, not measured results.

| Attribute | Target |
|---|---|
| Query latency, KNOWLEDGE, p95, time-to-first-token (streaming) | ≤ 1.5 s |
| Query latency, KNOWLEDGE, p95, complete answer | ≤ 6 s |
| Query latency, HYBRID with one live tool, p95 | ≤ 8 s |
| Retrieval stage (embed + vector + keyword + fuse + rerank), p95 | ≤ 400 ms |
| Ingestion freshness (contact received → searchable) | ≤ 5 min streaming, ≤ 1 cadence interval batch |
| Design capacity | 10M verbatims, 100 tenants, 50 concurrent queries per API replica |
| Availability of read path when LLM provider is down | Degraded "evidence-only" answers, no 5xx |
| Authorization leak rate | 0 (hard CI gate) |

---

## 2. Repository inspection: current state

What exists, verified by reading the files:

| Area | State |
|---|---|
| `docs/project-architecture-proposal.md` | Detailed capstone plan: Postgres + pgvector, Postgres-based property graph, deterministic complexity detector + LLM Query Planner that only plans, RRF hybrid retrieval, citation validation, numeric verification, Poisson detection, eval gate. **Sound; this design keeps all of it.** |
| `backend/src/ccvie/config.py` | 12 settings. Missing embedding dimension, retrieval, security, tool, cache, observability settings. |
| `backend/src/ccvie/contracts/` | `entities.py`, `insight.py`, `query.py`, `router.py`. `RouteDecision` has only `graph`/`vector`. No answer/claim/citation, tool, or auth contracts. |
| `backend/src/ccvie/{data_foundation,router,retrieval_gen,evaluation}` | All one-line stub files. `api.py` is an empty FastAPI app. |
| `backend/pyproject.toml` | Only fastapi, pydantic-settings, uvicorn. The venv has more installed than is declared. |
| `backend/tests/` | One unit test (`test_contracts.py`). Integration and eval folders empty. |
| `db/migrations/`, `db/seed/` | Empty (`.gitkeep` only). |
| `frontend/` | Next.js App Router, shadcn/ui, insight feed + drill-down + routing page, all on mocks. `api-client.ts` is shaped for a later HTTP swap. |
| `data/consumer_care_verbatims_1000.csv` | 1,000 synthetic contacts, 6 products, 19 packs, 4 regions (India), 12 issue types, Jan–Jun 2026. **Only 69 distinct verbatim texts.** No tenant or access attributes. Contains the planted South/Leakage cluster above. |
| `data/golden/` | Uses a **different vocabulary** (Crunchy Chips, Pacific Northwest, Seal Failure) from the CSV. `router_labeled_queries.json` contains the same query with two different expected routes, and stores `predictedRoute` inside ground truth. `planted_issue_ground_truth.json` stores `expectedLeadTimeDays`, which the proposal explicitly forbids. |
| `docker-compose.yml` | `pgvector/pgvector:pg16` only. |
| CI | No `.github/workflows/` yet. |

Consequences for this design:

1. The backend is effectively greenfield, so the structure can be set correctly now at low cost.
2. The golden sets must be rebuilt against one vocabulary before any evaluation number means
   anything (Section 22.4).
3. With 69 distinct texts, retrieval metrics on the current CSV would be inflated and near-
   meaningless; the generator must add paraphrase diversity (Section 22.4). The duplication does make
   a good embedding-cache demonstration (≈93% hit rate on ingest).

---

## 3. System context and components

### 3.1 Context

```
                        ┌───────────────────────────┐
  Care analysts,        │  Identity Provider (OIDC)  │   dev: local signed-JWT issuer
  Quality managers ───► │  users, roles, tenant claim│
  (browser)             └─────────────┬─────────────┘
        │                             │ JWT
        ▼                             ▼
┌───────────────┐   BFF (httpOnly  ┌────────────────────────────────────────────────┐
│ Next.js UI    │── cookie → JWT) ►│ CCVIE Query API  (FastAPI, stateless)          │
│ feed, ask,    │◄── JSON / SSE ───│  authn → policy → orchestrate → verify → respond│
│ drill-down    │                  └──┬──────────┬───────────┬────────────┬─────────┘
└───────────────┘                     │          │           │            │
                                      ▼          ▼           ▼            ▼
                           ┌──────────────┐ ┌─────────┐ ┌──────────┐ ┌──────────────────┐
                           │ PostgreSQL   │ │ Redis   │ │ Model    │ │ Tool Gateway      │
                           │ + pgvector   │ │ cache,  │ │ serving  │ │ (in API process)  │
                           │ verbatims,   │ │ queue,  │ │ embed /  │ │ registry, authz,  │
                           │ FTS, graph,  │ │ rate    │ │ rerank / │ │ MCP client        │
                           │ aggregates,  │ │ limits  │ │ NLI      │ └────────┬─────────┘
                           │ audit, RLS   │ └─────────┘ └──────────┘          │ MCP (streamable HTTP)
                           └──────▲───────┘      ▲                            ▼
                                  │              │                 ┌─────────────────────────┐
                      ┌───────────┴──────────────┴──┐              │ Enterprise MCP servers   │
  Contact sources ──► │ Ingestion API + Workers      │              │ (synthetic stand-ins)    │
  (batch files,       │ validate → redact → dedupe → │              │ care-ops (live volume)   │
   contact events)    │ persist → embed → index →    │              │ supply-chain (batches)   │
                      │ graph upsert → aggregate     │              │ quality-cases (tickets)  │
                      └──────────────┬──────────────┘              └─────────────────────────┘
                                     ▼
                      ┌─────────────────────────────┐        ┌───────────────────────────┐
                      │ Detection Scheduler          │        │ LLM provider(s)           │
                      │ Poisson / low-volume → insights│      │ via LLMClient port        │
                      └─────────────────────────────┘        └───────────────────────────┘

  Cross-cutting: OpenTelemetry traces → collector → trace backend; Prometheus metrics; JSON logs.
```

### 3.2 Components

| Component | Responsibility | Deployable unit | Scales on |
|---|---|---|---|
| **Frontend** (Next.js) | Feed, ask/investigate, drill-down, action confirmation. Backend-for-frontend route handlers hold the session and forward a JWT. | `frontend` container | Requests |
| **Query API** | AuthN, policy, orchestration graph, SSE streaming, response assembly | `api` container | RPS / p95 latency |
| **Orchestrator** (LangGraph, in API) | Understand → route → execute (fan-out) → context → generate → verify | library inside `api` | with API |
| **Retrieval service** (library) | Vector, keyword, graph, structured retrievers; fusion; rerank | library inside `api`; retrievers talk to Postgres | with API; DB read replicas |
| **Tool Gateway** (library) | Registry, authorization, schema validation, MCP client, circuit breakers, confirmation workflow | library inside `api` | with API |
| **Model serving** | Embedding, reranker, NLI/groundedness models behind HTTP | `models` container (CPU in dev, GPU optional) | Model QPS |
| **Ingestion API** | Accept batch manifests and contact events, enqueue | `api` route group or separate `ingest-api` | Event rate |
| **Ingestion workers** | Validate, redact, dedupe, persist, graph upsert | `ingest-worker` | Queue depth |
| **Embedding workers** | Batch embed with cache, write vectors | `embed-worker` | Queue depth |
| **Detection scheduler** | Aggregate cells, statistical scan, write insights | `detector` (singleton via Postgres advisory lock) | Not horizontally; partition by tenant if needed |
| **MCP servers** | Synthetic enterprise systems | one container each | Independently |
| **PostgreSQL + pgvector** | System of record for CCVIE data | `db` (+ replicas in prod) | Vertical, read replicas, partitioning |
| **Redis** | Cache, job queue, rate-limit counters, circuit-breaker state | `redis` | Vertical / cluster |
| **OTel collector + trace UI + Prometheus** | Observability | `otel-collector`, `jaeger`, `prometheus` | — |

The backend stays **one Python codebase with several entrypoints** (API, workers, scheduler). Each
entrypoint is its own container and scales on its own. This keeps the proposal's single-package
simplicity and still gives independent scaling. Section 28 (D13) covers the trade-off.

---

## 4. End-to-end query data flow

```
POST /v1/query {text, conversation_id?, filters?}
 │
 1  AuthN            verify JWT (iss, aud, exp, signature via JWKS) → Principal
 2  Policy           Principal → AccessFilter {tenant_id, regions, brands, max_classification}
 │                   deny-by-default; computed once, immutable for the request
 3  Guard            size limits, rate limit (per user + tenant), input normalization
 4  Understand       follow-up rewrite (conversation state) → scope check (scope.yaml)
 │                   → entity resolution (alias dict → pg_trgm → embedding)
 5  Route            deterministic features + rules → RouteDecision + confidence
 │                   low confidence / complex → LLM Query Planner → validated plan
 6  Execute (fan-out, parallel, each with its own timeout)
 │     KNOWLEDGE      → HybridRetriever(AccessFilter): vector ∥ keyword ∥ graph ∥ structured
 │                      → RRF fusion → rerank → top-k evidence
 │     REAL_TIME      → ToolGateway.call(read tool, principal)
 │     TRANSACTIONAL  → ToolGateway.propose(write tool) → PendingAction (not executed)
 7  Post-filter      assert every evidence item satisfies AccessFilter (fail closed)
 8  Context          dedupe, diversify, budget tokens, assign citation handles [S#] [F#] [T#]
 9  Generate         LLMClient.generate(structured schema) → claims[] with handles
10  Verify           citation membership → numeric trace → claim support (NLI) → state
11  Respond          QueryResponse {answer_state, claims, sources, route, groundedness,
 │                   pending_actions, degraded, usage, trace_id}; audit_log row written
 ▼
UI renders claims; citation chips fetch verbatim text by ID from /v1/verbatims (authz-checked),
never from LLM output. Pending actions show a confirmation dialog → POST /v1/actions/{id}/confirm.
```

Pure-structured questions ("how many leakage complaints in South last month?") can skip step 9:
the answer is rendered from a deterministic template over the SQL result, with the query result as
its citation. This saves an LLM call and removes the chance of a numeric hallucination
(`GENERATION_SKIP_FOR_STRUCTURED=true`).

---

## 5. Ingestion architecture

### 5.1 Pipeline

```
Sources                      Landing                 Processing (async workers)                    Indexes
───────                      ───────                 ─────────────────────────                     ───────
Batch file (CSV/JSONL) ─┐    raw_contacts            1 schema validate (Pydantic)  ── invalid ──►  dead_letters
  manifest + checksum   ├──► (append-only,  ──enqueue─► 2 normalize + taxonomy map
Contact event (HTTP/    │    restricted,             3 PII redact (before any derived copy)
  queue)               ─┘    short retention)        4 dedupe (idempotency key + content hash)
                                                     5 upsert verbatims (+ tsvector generated col)
                                                     6 outbox: embed_requested, graph_changed ───► embed-worker:
                                                     7 graph upsert (entity nodes/edges)             cache lookup by
                                                     8 aggregate-cell increment                      (model,version,hash)
                                                                                                     → miss: batch embed
                                                                                                     → write vector
                                                                                                     → bump index_version
```

### 5.2 Incremental ingestion

- **Idempotency:** every contact has a source-scoped key `(tenant_id, source_system, contact_id)`.
  Upserts use `ON CONFLICT ... DO UPDATE ... WHERE excluded.source_updated_at > verbatims.source_updated_at`,
  so replays and out-of-order delivery are safe.
- **Watermarks:** `source_watermarks(tenant_id, source, high_water_mark, last_run_id)`. Batch sources
  also record a file checksum in `ingestion_runs` so a re-uploaded file is a no-op.
- **Change propagation:** workers write domain events to an `outbox` table in the same transaction
  as the data change (transactional outbox). A relay publishes them to the queue. This avoids the
  "row committed, event lost" failure without distributed transactions.
- **Backfill / re-embedding:** a new embedding model gets a new `embedding_version`. Workers
  dual-write the new version into a parallel vector column set/table, evaluation runs against it,
  then `ACTIVE_EMBEDDING_VERSION` flips in config. Rollback is a config flip.
- **Deletes / retention:** soft-delete flag plus a purge job; purge cascades to embeddings, graph
  links and caches (by `index_version` bump).

### 5.3 Asynchronous processing

- Queue behind a `JobQueue` port; default adapter is Redis-backed (at-least-once, visibility
  timeout, retry with exponential backoff and jitter, max attempts → dead-letter). A Postgres
  `SKIP LOCKED` adapter is the zero-extra-infrastructure alternative; Kafka is the adapter for
  sustained streaming volume. The workers only see the port.
- Workers are stateless; batch size and concurrency come from config. Backpressure: the ingestion
  API returns `429` with `Retry-After` when queue depth exceeds `INGEST_MAX_QUEUE_DEPTH`.
- Poison messages go to `dead_letters` with the error and the payload hash; an admin endpoint
  replays them.

### 5.4 Embedding cache

- `embedding_cache(model_name, embedding_version, content_sha256, vector, created_at)`, primary key
  on the first three columns. Content is hashed **after** normalization and redaction.
- Used by ingestion and by query-time embedding (query embeddings are also cached in Redis with a
  TTL because query text is short-lived).
- Embedding calls are batched (`EMBED_BATCH_SIZE`) and deduplicated within the batch.

### 5.5 Chunking

Most verbatims are one to three sentences: **one verbatim = one chunk**. Long contacts (email
threads, call transcripts) are split with sentence windows (`CHUNK_MAX_TOKENS`,
`CHUNK_OVERLAP_TOKENS`). Every chunk keeps `verbatim_id` plus character offsets so a citation always
resolves to the original contact and highlights the exact span.

---

## 6. Data model

All tenant-owned tables carry `tenant_id` and have Postgres Row-Level Security enabled (Section 16).
Migrations remain plain SQL in `db/migrations/`.

| Table | Purpose / key columns |
|---|---|
| `tenants` | tenant registry, status, data-retention policy |
| `taxonomy_*` / seed | products, brands, categories, packs (+version), regions, countries, channels, issue types, issue categories, aliases |
| `raw_contacts` | append-only landing, restricted role only, short retention |
| `verbatims` | `id, tenant_id, source_system, contact_id, text_redacted, product_id, pack_id, region_id, channel, issue_type_id, sentiment, occurred_at, classification, content_sha256, fts tsvector GENERATED` — partitioned by `occurred_at` month at scale |
| `verbatim_chunks` | only for long contacts; `verbatim_id, ordinal, start_char, end_char, text` |
| `verbatim_embeddings` | `chunk_or_verbatim_id, tenant_id, embedding_version, embedding vector(EMBEDDING_DIMENSION)` + denormalized filter columns (region, brand, occurred_at) for filtered ANN |
| `embedding_cache` | Section 5.4 |
| `graph_nodes`, `graph_edges` | existing design, plus `tenant_id`; B-tree on `src`, `dst`, GIN on used `props` keys |
| `agg_daily_cells` | `(tenant_id, day, product, pack, region, issue_type, …) → count` |
| `insights` | detected emerging issues, statistic, baseline, supporting verbatim IDs |
| `insight_feedback` | existing design |
| `conversations`, `conversation_turns` | resolved filters per turn for follow-up rewrite; TTL-purged |
| `tool_invocations` | every tool call: tool, args hash, principal, status, latency, error class |
| `pending_actions` | proposed transactional calls awaiting confirmation; `idempotency_key`, `expires_at` |
| `ingestion_runs`, `source_watermarks`, `outbox`, `dead_letters` | ingestion control |
| `audit_log` | existing design plus `principal_id, tenant_id, route, source_ids_returned, tools_called` |

---

## 7. Vector architecture

- **Store:** pgvector, HNSW index, cosine distance. `halfvec` storage is an option once recall is
  verified, halving memory.
- **Sizing (estimate):** 10M vectors × 384 dims × 4 bytes ≈ 15 GB raw, plus HNSW graph overhead.
  This fits one well-provisioned Postgres node; beyond ≈50–100M vectors or high sustained ANN QPS,
  switch the `VectorStore` adapter to a dedicated engine (Section 24).
- **Filtered ANN:** access and metadata filters are applied **inside** the vector query, never
  after it in Python. Plain HNSW + `WHERE` post-filters inside the index scan and can return fewer
  than *k* rows for selective filters. Mitigations, in order:
  1. pgvector iterative index scans (`hnsw.iterative_scan`, pgvector ≥ 0.8) so the scan continues
     until *k* rows pass the filter.
  2. `tenant_id` list partitioning for large tenants (each partition has its own HNSW index, so
     tenant filtering is free).
  3. Exact scan fallback when the filter is very selective (planner estimate below
     `VECTOR_EXACT_SCAN_MAX_ROWS`), which is both correct and fast for small result sets.
- **Versioning:** `embedding_version` on every vector; queries only read `ACTIVE_EMBEDDING_VERSION`.
- **Query path:** query text → `EmbeddingModel.embed_query` (cached) → `VectorStore.search(vector,
  filter, k=RETRIEVAL_VECTOR_CANDIDATES)`.

---

## 8. Hybrid retrieval

```
AccessFilter + resolved-entity MetadataFilter  (mandatory argument to every retriever)
        │
        ├─► VectorRetriever     top N_v  (pgvector HNSW, filtered)
        ├─► KeywordRetriever    top N_k  (Postgres FTS; BM25 adapter optional)
        ├─► GraphRetriever      top N_g  (verbatims linked to the bounded subgraph)
        └─► StructuredRetriever facts    (SQL aggregates; not ranked, go to context as FACTS)
        │
        ▼
  Reciprocal Rank Fusion:  score(d) = Σ_r  w_r / (RRF_K + rank_r(d))      (RRF_K default 60)
        │   top M fused candidates (RERANK_CANDIDATES, default 40)
        ▼
  Reranker (cross-encoder behind Reranker port; timeout → keep RRF order, mark degraded)
        │
        ▼
  MMR / near-duplicate collapse (content hash + cosine > DEDUP_COSINE_MIN)
        │
        ▼
  top K evidence, K ≤ MAX_EVIDENCE_ITEMS  (a cap, not a target — existing rule)
```

Decisions:

- **Keyword search:** Postgres full-text search (`tsvector` generated column, GIN index,
  `websearch_to_tsquery`, `ts_rank_cd`). This is **BM25-like, not BM25**: it lacks BM25's term
  saturation and document-length normalization. It is good enough for short verbatims where exact
  tokens such as "500ml", "pump", "leak" carry the signal. A true-BM25 adapter (ParadeDB
  `pg_search` in Postgres, or OpenSearch) sits behind the same `KeywordIndex` port and is chosen
  only if the retrieval ablation shows a gap (Section 22.1).
- **Fusion:** RRF because it needs no score calibration across heterogeneous retrievers. Weights
  `w_r` are config values, default 1.0, tuned only against the retrieval set.
- **Metadata filtering** comes from two sources that are **merged with AND, never OR**: the
  access filter (security, from policy) and the query filter (relevance, from entity resolution or
  explicit UI filters). A query filter can narrow the access filter; it can never widen it.
- **Candidate depths** (`N_v`, `N_k`, `N_g`, `M`, `K`) are config, sized so the reranker sees
  ≤ 40 pairs, which keeps rerank latency inside the retrieval budget on CPU.
- **Thematic questions** ("what are people saying about pumps?") use a larger candidate pool,
  MMR diversity, and SQL facets (counts per issue type/region) so the answer covers themes rather
  than the ten most similar near-duplicates.

---

## 9. Graph architecture (Graph RAG)

Unchanged from the proposal in substance: a **PostgreSQL-based property graph model with
relational tables and SQL joins, with GraphRAG-style retrieval**. Local GraphRAG only.

- **Ontology** (from the synthetic data available): `Brand → Product → Pack(version) → Component →
  Supplier`, `Pack -replaced_by→ Pack`, `IssueType → IssueCategory`, `Region → Country`,
  `Insight → {Pack, Product, Region, IssueType}`. Supplier/Component/Plant/Batch nodes are
  synthetic additions produced by the generator so supply-chain questions are answerable.
- **Traversal:** bounded recursive CTE (`GRAPH_TRAVERSAL_MAX_DEPTH`, default 3 for query time,
  6 max), cycle-safe via a visited-path array, with `tenant_id` in every join (RLS enforces it too).
- **Output:** (a) a serialized subgraph (typed nodes/edges, ≤ `GRAPH_CONTEXT_MAX_EDGES`) that
  becomes `[F#]` facts in the context, and (b) a ranked list of verbatims attached to subgraph
  entities, fed into RRF.
- **Canonical question:** "Is the 500ml New Bottle leakage in South showing up anywhere else, and
  do other packs share its component supplier?" → `Pack → Component → Supplier → Component → Pack
  → Region`, then verbatim evidence for each related pack.
- **Swap path:** `GraphStore` port. A dedicated graph engine is a future adapter, not in scope.

---

## 10. Query routing

### 10.1 Two axes, one decision

The requirement's four classes describe **where the data comes from**. The existing proposal's
routes describe **how knowledge is retrieved**. They are different axes, so the contract carries
both:

```
RoutingDecision          (the legacy RouteDecision enum is removed in Phase 4, ADR-0005)
  query_class:  KNOWLEDGE | REAL_TIME_DATA | TRANSACTIONAL | HYBRID
  strategies:   set of {VECTOR, KEYWORD, GRAPH, STRUCTURED}      (when knowledge is needed)
  tools:        list of registry tool_ids                         (when live data / actions needed)
  confidence:   0..1
  decided_by:   RULES | PLANNER | FALLBACK
  reasons:      list of feature names that fired                 (for the routing UI and eval)
```

| Class | Meaning | Example (synthetic data) | Data sources |
|---|---|---|---|
| KNOWLEDGE | Answerable from CCVIE's indexed store: verbatims, graph, aggregates, insights | "What are customers saying about the 500ml New Bottle in South?" | Hybrid retrieval, graph, SQL |
| REAL_TIME_DATA | Needs current state from a system of record CCVIE does not index | "How many leakage contacts came in today for FreshGlow?" / "Which batches shipped to South this week?" | Read MCP tools |
| TRANSACTIONAL | Changes state in an external system | "Open a quality investigation for the South leakage insight" | Write MCP tool (confirmation required) |
| HYBRID | Needs two or more of the above | "Summarize the South leakage complaints and open a QA case with the top evidence" | Retrieval + tools, fan-out |

`HYBRID` is **derived**, not predicted independently: it is the class when the execution plan needs
more than one data-source family. This removes a whole category of classifier disagreement.

### 10.2 Routing pipeline

```
features(query, resolved_entities, conversation)       deterministic, <5 ms
  action_verbs           create|open|raise|escalate|assign|notify|subscribe → TRANSACTIONAL signal
  recency_markers        today|right now|live|current|this hour|open cases  → REAL_TIME signal
  tool_entity_match      does a registered read tool cover the requested metric/entity?
  aggregate_markers      how many|count|trend|compare|top                   → STRUCTURED
  relationship_markers   related|also affected|same supplier|elsewhere      → GRAPH
  thematic_markers       what are people saying|themes|why                  → VECTOR+KEYWORD
  entity_coverage, intent_count, conflicting_signals, missing_parameters
        │
        ▼
complexity + confidence (existing proposal rules, thresholds in config)
        │
   SIMPLE & confidence ≥ ROUTER_CONFIDENCE_MIN ─► rule table → RouteDecision(decided_by=RULES)
        │
   otherwise ─► LLM Query Planner (structured output, enum-constrained operations and tool_ids
               drawn ONLY from the principal's permitted registry subset)
               → Pydantic validation → plan → RouteDecision(decided_by=PLANNER)
        │
   planner fails / times out / invalid ─► FALLBACK: KNOWLEDGE with VECTOR+KEYWORD, and a
               clarification prompt if a transactional verb was present (never guess an action)
```

Why deterministic first: most traffic is simple; rules cost nothing, are reproducible, and are
fully unit-testable. The LLM is spent only on the queries rules cannot decide confidently. A
second LLM classifier is **not** added; the existing Query Planner already produces a plan whose
operation families determine the class.

### 10.3 Safety properties of routing

- The router **never** decides authorization. A query routed to a tool the user cannot use still
  fails at the Tool Gateway.
- The planner only sees tools the principal is allowed to use, so it cannot even propose others.
- A TRANSACTIONAL route never executes during the query; it produces a `PendingAction`.

---

## 11. Enterprise API / tool routing and the MCP registry

### 11.1 Why MCP

MCP gives a standard contract for tool discovery, JSON-schema'd arguments and results, and
transport. Enterprise systems can be exposed once and reused by CCVIE and by other agents. The
cost is an extra network hop and a protocol surface to secure (Section 15.4). CCVIE therefore
uses MCP **behind its own Tool Gateway**, so a direct REST adapter can replace any MCP server
without touching the orchestrator.

### 11.2 Registry

`backend/src/ccvie/tools/registry.yaml` is the source of truth, loaded and validated into
`ToolSpec` models at startup. The registry, **not the MCP server**, owns descriptions and
permissions; server-advertised descriptions are never shown to the LLM (tool-poisoning defence).

```yaml
- tool_id: care_ops.get_live_contact_volume
  server: care-ops                 # resolved to a URL from config
  version: 1
  category: READ_REALTIME          # READ_REFERENCE | READ_REALTIME | WRITE
  description: >-                  # registry-owned text shown to the planner
    Current contact counts for a product/pack/region/issue over a recent window.
  input_model: LiveVolumeArgs      # Pydantic model in contracts/tools.py
  output_model: LiveVolumeResult
  required_scopes: [tools:care_ops:read]
  required_roles: []               # any role with the scope
  tenant_scoped: true              # gateway injects tenant from Principal
  side_effects: false
  requires_confirmation: false
  idempotent: true
  timeout_ms: 1500
  retries: 2
  cache_ttl_s: 30
  rate_limit_per_min: 120
  output_classification: INTERNAL
  owner: care-operations
  enabled: true
```

At startup (and periodically) the gateway calls each server's `list_tools` and compares the
advertised input schema against `input_model`. On mismatch the tool is disabled and an alert
metric fires (schema-drift detection), rather than calling a tool with a contract the code does not
understand.

### 11.3 Representative tools (implemented)

Only three servers with four tools are implemented, as synthetic stand-ins with seeded data:

| Server | Tool | Category | Purpose |
|---|---|---|---|
| `care-ops` | `get_live_contact_volume` | READ_REALTIME | Live counts; confirms whether an insight is still growing today |
| `supply-chain` | `get_batch_shipments` | READ_REALTIME | Which pack batches shipped to which regions, for recall scoping |
| `quality-cases` | `create_investigation_case` | WRITE | Opens a QA case with insight ID and evidence IDs |
| `quality-cases` | `get_case_status` | READ_REFERENCE | Reads a case back |

Every other enterprise integration (CRM, ERP, notifications) is documented in the registry format
but not implemented.

### 11.4 Invocation flow

```
planner / rule table proposes ToolCall(tool_id, args)
  1 registry lookup; enabled? healthy (circuit closed)?
  2 authorize: principal has required_scopes AND required_roles       ── deny → 403 in trace, not LLM
  3 validate args against input_model (reject extra fields)
  4 inject server-side context: tenant_id, principal_id, request_id    (never taken from LLM args)
  5 WRITE?  → persist PendingAction(idempotency_key, args, expires_at) → return to UI; STOP
            → on POST /v1/actions/{id}/confirm: re-authorize, execute once with idempotency key
  6 call MCP server (streamable HTTP, service credential + on-behalf-of user token), timeout,
    retries only if idempotent, circuit breaker per tool
  7 validate output against output_model; truncate to TOOL_OUTPUT_MAX_BYTES
  8 wrap as untrusted ToolResult → context handle [T#]; record tool_invocations + audit_log
```

MCP servers **re-check** the tenant and scopes on their side (zero trust); the gateway check is not
the only one.

---

## 12. Context construction

The context builder turns evidence into a bounded, labeled, injection-resistant prompt section.

1. **Assemble** evidence items from retrieval (`VerbatimEvidence`), structured results
   (`FactEvidence`: counts, trends, graph facts) and tools (`ToolEvidence`).
2. **Collapse** near-duplicates (important with this dataset) and keep a `duplicate_count` so the
   model can say "12 contacts report…" with the count coming from data.
3. **Budget** tokens per section (`CONTEXT_BUDGET_TOKENS`, split by `CONTEXT_SHARE_*`): facts
   first (small, high value), then verbatims by rerank score, then tool results. Truncation is
   deterministic.
4. **Label** each item with an opaque handle: `[S1]..[Sn]` verbatims, `[F1]..` facts, `[T1]..` tool
   results. The handle → source-ID map stays server-side; the LLM never sees database IDs, so it
   cannot fabricate a plausible-looking one.
5. **Isolate untrusted text**: every verbatim and tool result is wrapped in explicit data
   delimiters, with the system instruction that content inside them is data and never
   instructions. Verbatim text is also scanned for injection patterns; matches are kept as
   evidence but flagged, and logged.
6. **Metadata per item**: product, pack, region, date, channel. This lets the model state scope
   precisely without inventing it.

Prompt templates are versioned files under `retrieval_gen/prompts/`; the template version is part
of the LLM cache key and the audit record.

---

## 13. LLM generation

- **Port:** `LLMClient.generate(messages, response_schema, max_tokens, temperature, metadata) →
  LLMResult{parsed, usage, model, latency}` plus `stream(...)`. Adapters: Anthropic, OpenAI-
  compatible, and a deterministic `FakeLLM` for tests/CI. Provider and model names only in config.
- **Structured output:** the model returns JSON matching `GeneratedAnswer{claims: [{text,
  citations: [handle], fact_refs: [handle]}], unanswerable_reason?}`. Free-text answers are not
  accepted; the prose the user reads is assembled from verified claims.
- **Model tiering:** `LLM_MODEL_NAME` (synthesis), `LLM_PLANNER_MODEL_NAME` (planning, can be a
  smaller model), `LLM_JUDGE_MODEL_NAME` (offline evaluation only).
- **Determinism:** temperature 0 for planning and synthesis; seeds where the provider supports them.
- **Streaming:** SSE events `route`, `evidence`, `claim` (after each claim passes verification),
  `pending_action`, `done`, `error`. Claims stream after verification, so an unverified claim is
  never shown and then withdrawn.
- **Failover:** a secondary provider can be configured; on circuit-open the orchestrator switches,
  or degrades to evidence-only mode (Section 20).

---

## 14. Hallucination and groundedness checks

Run in order; each is cheaper and more deterministic than the next.

| # | Check | Method | On failure |
|---|---|---|---|
| V1 | Schema | Pydantic parse of `GeneratedAnswer` | one repair retry, then evidence-only |
| V2 | Citation membership | every handle exists in this request's context map | drop claim |
| V3 | Citation required | every factual claim has ≥ 1 citation | drop claim |
| V4 | Numeric trace | every number in a claim appears in a cited `[F#]`/`[T#]` value (normalized: 45 = "forty-five", % tolerance 0) | drop claim |
| V5 | Entity consistency | products/packs/regions named in a claim appear in its cited items' metadata | drop claim |
| V6 | Claim support | NLI model (`GroundednessChecker` port) scores entailment of claim by concatenated cited evidence; `≥ GROUNDEDNESS_MIN_ENTAILMENT` | drop claim |
| V7 | Coverage | if > `GROUNDEDNESS_MAX_DROPPED_RATIO` of claims dropped | answer_state = PARTIAL or INSUFFICIENT_EVIDENCE |

Result states: `ANSWER`, `PARTIAL`, `CLARIFICATION`, `INSUFFICIENT_EVIDENCE`, `REFUSAL`. The response
carries `groundedness {score, checked_claims, dropped_claims[{text, reason}]}` so the UI and the
audit log can show exactly what was removed and why.

Offline evaluation additionally uses an LLM judge for faithfulness (Section 22). The online path
uses NLI because it is cheaper, faster, local and deterministic. The judge is only used to
calibrate the NLI threshold.

---

## 15. Security

### 15.1 Trust boundaries

```
Untrusted: user query text, verbatim text, tool outputs, MCP server metadata, LLM output
Trusted:   JWT claims after signature verification, registry.yaml, config, policy code, DB RLS
```

LLM output is **data to be validated**, never an instruction to the system: it cannot choose a
tenant, widen a filter, pick an unregistered tool, or execute a write.

### 15.2 Controls

| Threat | Control |
|---|---|
| Unauthenticated access | OIDC JWT on every route except health; JWKS rotation; short-lived tokens |
| Token theft in browser | Next.js BFF keeps tokens in httpOnly, Secure, SameSite cookies; the browser never holds a bearer token |
| Cross-tenant data access | Section 16: policy filter + Postgres RLS + post-filter assertion + cache-key scoping |
| Prompt injection via verbatims | Delimited untrusted blocks, injection-pattern flagging, no tool authority derived from content, structured output + verification |
| Prompt injection via tool output | Same as verbatims; tool outputs are schema-validated and size-limited |
| Tool poisoning (malicious MCP descriptions) | Registry-owned descriptions, schema pinning and drift detection |
| Unauthorized actions | WRITE tools need scope + role + explicit human confirmation + idempotency key; confirmation re-authorizes |
| SQL injection | Parameterized asyncpg queries only; LLM never produces SQL; read-only DB role for query path |
| PII leakage | Ingestion-time redaction (email, phone, order no., names) before any derived copy; logs never contain verbatim text or prompts by default; `raw_contacts` restricted role |
| Secrets | Env/secret manager only via `Settings`; `.env` gitignored; secret scanning in CI |
| Abuse / cost attacks | Per-user and per-tenant rate limits and token budgets; input length caps |
| Supply chain | Pinned dependencies (lockfile), dependency and container scanning in CI |
| Transport | TLS at ingress; service-to-service tokens (mTLS in production) for MCP servers and model serving |

### 15.3 Database roles

`ccvie_ingest` (write verbatims, embeddings, graph), `ccvie_query` (read-only on data tables, write
only `audit_log`, `conversations`, `tool_invocations`, `pending_actions`), `ccvie_admin`
(migrations). RLS policies apply to `ccvie_ingest` and `ccvie_query`; neither has `BYPASSRLS`.

### 15.4 MCP-specific

Service authentication between gateway and servers, user identity forwarded as a separate
on-behalf-of token, servers enforce tenant scoping, per-server network policy (servers cannot reach
the CCVIE database), response size limits.

---

## 16. Authorization

### 16.1 Model

RBAC for capabilities plus ABAC for data scope:

```
Principal (from verified JWT, never from request body)
  user_id, tenant_id, roles[], scopes[], attributes {regions[], brands[], clearance}

Roles (synthetic):
  care_analyst       read verbatims + insights within assigned regions/brands
  quality_manager    above + tools:quality_cases:write + feedback
  regional_manager   read within own region only
  executive          aggregates and insights only; no raw verbatim text (clearance=INTERNAL)
  ingest_service     ingestion endpoints only
  platform_admin     tool registry and dead-letter admin; no data read by default
```

### 16.2 Enforcement points (defense in depth)

```
1 API dependency      route requires capability (e.g. query:ask, actions:confirm)
2 Policy engine       Principal → AccessFilter (pure function, deny-by-default, unit-tested matrix)
3 Retriever ports     AccessFilter is a REQUIRED typed argument; there is no overload without it
4 Postgres RLS        SET LOCAL app.tenant_id / app.regions per transaction; policies on every
                      tenant table → a missing WHERE clause still cannot leak across tenants
5 Post-filter         every evidence item re-checked against AccessFilter; violation = fail closed,
                      500 + security alert (it indicates a bug)
6 Tool Gateway        scopes/roles per tool; tenant injected server-side
7 MCP server          re-checks tenant and scope
8 Response render     verbatim text for citations fetched via /v1/verbatims, which re-applies 1-5
9 Cache               every cache key includes hash(AccessFilter); no cross-principal reuse
                      unless the filters are identical
```

The LLM participates in none of these. Classification downgrades (executive sees counts, not
text) are applied at retrieval: the retriever returns `FactEvidence` only, so the text never reaches
the prompt.

---

## 17. Observability

- **Tracing:** OpenTelemetry. One trace per request; spans: `authn`, `policy`, `understand`,
  `route`, `plan`, `retrieve.vector`, `retrieve.keyword`, `retrieve.graph`, `retrieve.structured`,
  `fuse`, `rerank`, `tool.<tool_id>`, `context`, `llm.generate`, `verify.<check>`, `respond`. Span
  attributes: tenant, route class, candidate counts, cache hit, token counts, model config key (not
  text). Propagated to MCP servers and workers via W3C trace context.
- **Logging:** JSON lines via stdlib `logging` with a JSON formatter, one event per stage, correlated by `trace_id`/`request_id`. Verbatim
  text, prompts and completions are **not** logged by default; `LOG_PROMPTS=true` is for local debug
  and logs redacted text only.
- **Metrics (Prometheus):**
  - `ccvie_request_latency_seconds{route_class,stage}` histogram
  - `ccvie_llm_tokens_total{purpose,direction}` and `ccvie_llm_cost_usd_total{purpose,tenant}`
    (cost from a per-model price table in config)
  - `ccvie_retrieval_candidates{retriever}`, `ccvie_cache_hits_total{cache}`
  - `ccvie_tool_calls_total{tool_id,status}`, `ccvie_tool_latency_seconds{tool_id}`
  - `ccvie_route_decisions_total{class,decided_by}`
  - `ccvie_groundedness_score` histogram, `ccvie_claims_dropped_total{reason}`
  - `ccvie_answer_state_total{state}`, `ccvie_degraded_total{component}`
  - ingestion: queue depth, lag (`now - oldest unprocessed`), DLQ size, embed cache hit ratio
- **Per-request usage** (`latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `cache_hits`) is also
  returned in the API response and written to `audit_log`.
- **Dashboards/alerts** (documented, provisioned locally): p95 latency per class, error budget burn,
  groundedness drop, tool failure rate, ingestion lag, security post-filter violations (page on any).

---

## 18. Caching

| Cache | Store | Key | TTL / invalidation |
|---|---|---|---|
| Document embeddings | Postgres `embedding_cache` | model, version, content hash | permanent; new version = new key |
| Query embeddings | Redis | model, version, normalized query hash | 24 h |
| Retrieval results | Redis | normalized query, merged filters, **AccessFilter hash**, `index_version`, retrieval config hash | 10 min; `index_version` bumps on every ingestion commit |
| LLM answers | Redis | prompt template version, model key, evidence-handle→ID set hash, **AccessFilter hash**, query hash | 1 h; only temperature 0; never for answers with tool results |
| Read tool results | Redis | tool_id, validated args, tenant, principal scope hash | `cache_ttl_s` per tool (e.g. 30 s); WRITE tools never cached |
| Entity resolution / taxonomy | in-process LRU | alias | reload on taxonomy version change |
| Provider prompt caching | LLM provider | static system prompt prefix | provider-managed |

**Semantic caching (reusing answers for "similar" queries) is intentionally not used.** Near-miss
queries can differ in region or date by one token and get a wrong, confidently cited answer.
It can be revisited with a strict similarity threshold and eval evidence.

---

## 19. Cost optimization

1. Deterministic routing first; the planner LLM runs only for complex/low-confidence queries.
2. Structured questions are answered from SQL with a template, without synthesis LLM calls.
3. Rerank + dedupe shrink the context; budgets cap tokens per request.
4. Model tiering: smaller model for planning, larger only for synthesis; judge model offline only.
5. Caches above, plus provider prompt caching for the fixed system prompt and schema.
6. Local CPU models for embedding, reranking and NLI (no per-call cost).
7. Embedding cache and batch embedding on ingestion.
8. Per-tenant token budgets and quotas (`TENANT_DAILY_TOKEN_BUDGET`) with a `429`-style soft stop.
9. Cost is a first-class metric per request, tenant and purpose, so regressions are visible in the
   eval report (cost per answered query is reported alongside quality).

---

## 20. Failure handling

### 20.1 Mechanisms

- **Timeouts** per stage and an overall request deadline (`REQUEST_DEADLINE_MS`); remaining budget
  propagates to downstream calls.
- **Retries** with exponential backoff and jitter, only for idempotent operations, bounded by the
  remaining deadline.
- **Circuit breakers** per LLM provider, per MCP tool, per model-serving endpoint (state in Redis so
  replicas agree).
- **Bulkheads:** separate connection pools / concurrency limits for DB, model serving, LLM and
  tools, so a slow tool cannot exhaust DB connections.
- **Idempotency:** ingestion keys; `pending_actions.idempotency_key` passed to write tools.
- **Health:** `/healthz` (process), `/readyz` (DB pool, Redis, migrations at expected version,
  registry loaded). Model serving and MCP servers expose their own.

### 20.2 Degradation matrix

| Failure | Behaviour | Response marker |
|---|---|---|
| Reranker unavailable | keep RRF order | `degraded: [reranker]` |
| Vector store / embedding service unavailable | keyword + graph + structured only | `degraded: [vector]` |
| Keyword search error | vector + graph only | `degraded: [keyword]` |
| Graph traversal hits depth/time cap | truncated subgraph, flagged | `degraded: [graph_truncated]` |
| One read tool fails in HYBRID | answer from remaining sources, claim about missing source | `degraded: [tool:<id>]` |
| Write tool fails on confirm | action state `FAILED`, retry allowed with same idempotency key | action status |
| Planner fails | FALLBACK route (Section 10.2) | `decided_by: FALLBACK` |
| Synthesis LLM unavailable | failover provider, else evidence-only answer (facts + top verbatims, no generated claims) | `answer_state: EVIDENCE_ONLY` |
| Groundedness checker unavailable | `VERIFY_FAIL_MODE=closed` (default): evidence-only; `open`: claims shown as "unverified" | `verification: unavailable` |
| DB unavailable | `/readyz` fails; 503 with `Retry-After` | — |
| Ingestion record invalid | dead-letter; batch continues | run report |
| Worker crash mid-batch | message redelivered after visibility timeout; idempotent upsert | — |

---

## 21. Scalability and deployment topology

```
                       ┌──────────── ingress / TLS ────────────┐
                       ▼                                         ▼
               frontend ×N                                   api ×N  ──────────────┐
                                                               │                   │
          ┌──────────────────┬─────────────────┬──────────────┼──────────┐        │
          ▼                  ▼                 ▼              ▼          ▼        ▼
     pgbouncer          redis (cache,     models ×N       mcp-care-ops  mcp-supply  mcp-quality
          │              queue, limits)   (embed,rerank,    ×N           ×N          ×N
   ┌──────┴──────┐                         NLI; GPU opt.)
   ▼             ▼
 postgres     read replicas ◄── query path reads
 primary      (retrieval)
   ▲
   │ writes
 ingest-worker ×N   embed-worker ×N   detector ×1 (advisory lock)   outbox-relay ×1..N
```

- Every box is a separate container built from the same backend image with a different
  entrypoint (except frontend, MCP servers, models). Docker Compose locally (`--scale` works for the
  stateless ones); the same images map one-to-one onto any container orchestrator.
- **Stateless API:** no in-process session state; conversation state lives in Postgres, caches in
  Redis.
- **Read/write split:** the query path uses a read-replica DSN (`DATABASE_READ_URL`); replication
  lag is acceptable because ingestion freshness targets are minutes.
- **Partitioning:** `verbatims` and `verbatim_embeddings` by month; large tenants by list partition.
- **Model serving** is its own service so API replicas do not each load models into memory, and so
  it can move to GPU independently. In local dev the `EmbeddingModel` adapter can run in-process.
- **Hot path isolation:** ingestion and query use different DB roles, pools and (in production)
  different replicas.

---

## 22. Evaluation

### 22.1 Metrics

| Metric | Definition | Dataset | Gate in CI |
|---|---|---|---|
| Retrieval precision@k | relevant ∩ top-k / k (graded relevance ≥ 1) | retrieval set | yes |
| Retrieval recall@k | relevant ∩ top-k / relevant | retrieval set | yes (`EVAL_RECALL_AT_20_MIN`) |
| MRR | mean 1/rank of first relevant | retrieval set | yes |
| nDCG@10 | graded | retrieval set | report |
| Ablation | the above for vector-only, keyword-only, vector+keyword RRF, +graph, +rerank | retrieval set | report |
| Routing accuracy | exact match of `query_class`; per-class precision/recall; confusion matrix; strategy-set Jaccard | routing set | yes |
| Always-KNOWLEDGE baseline | routing accuracy if every query went to vector RAG | routing set | report |
| Tool selection accuracy | correct tool_id set and valid args | tool set | yes |
| Tool success rate | successful calls / attempted, under normal and fault-injected runs | tool set | yes (normal); report (faults) |
| Authorization correctness | denied when it should be; allowed when it should be | security set | yes = 100% |
| Leak rate | foreign-tenant or out-of-scope source IDs in any response | security set | yes = 0 |
| Citation correctness | precision: cited sources that support their claim; recall: expected sources cited | answer set | yes (precision) |
| Answer faithfulness | supported claims / total claims (NLI in CI; LLM judge nightly) | answer set | yes (NLI) |
| Answer relevance | judge score of answer vs question (nightly), plus required-fact coverage (CI, deterministic) | answer set | CI: fact coverage |
| Numeric correctness | exact match of every number vs known answer | numeric set | yes |
| Injection resistance | responses that follow injected instructions / leak system prompt | adversarial set | yes = 0 |
| Detection lead time, FPR | existing | planted issues | yes (existing) |
| Latency / cost per query | p50/p95, USD | all sets | report, alert on regression |

### 22.2 Harness

- `evaluation/runner.py` loads a dataset, runs the **real orchestrator** against the fixture DB with
  configurable adapters, and writes `eval-report.json` + markdown summary.
- **CI mode:** `FakeLLM` (scripted, deterministic) for generation-dependent tests, real retrieval,
  real routing rules, fake MCP servers. Deterministic metrics gate the build.
- **Nightly mode:** real LLM, LLM-judge metrics, fault injection; results trended, not gating
  (nondeterminism and cost).
- Thresholds live only in `config.py` as `EVAL_*_MIN` / `EVAL_*_MAX` (existing rule).

### 22.3 Representative datasets (`data/golden/`, committed, small)

| File | Contents | Size target |
|---|---|---|
| `retrieval_set.jsonl` | query, filters, principal, graded relevant verbatim IDs | 60 queries |
| `routing_set.jsonl` | query, expected class, strategies, tools; includes ambiguous and multi-signal cases | 120 (30/class) |
| `answer_set.jsonl` | query, principal, required facts, expected source IDs, expected answer_state | 40 |
| `numeric_set.jsonl` | count/trend/compare questions with exact answers | 20 |
| `tool_set.jsonl` | query, expected tool calls + args, scripted server responses incl. failures | 25 |
| `security_set.jsonl` | principal, query, forbidden source IDs / tools, expected denial | 30 |
| `adversarial_set.jsonl` | injection-bearing verbatims, PII probes, out-of-scope asks | 25 |
| `planted_issue_ground_truth.json` | onset dates (no expected lead time) | existing, fixed |
| `eval_fixture.jsonl` | the fixed small corpus the CI DB is loaded with | ≈2–5k rows |

### 22.4 Synthetic data plan

`data/generators/` is extended (not replaced) to:

1. Use the CSV's vocabulary as the single taxonomy (`taxonomy_config.yaml`), and rebuild
   `data/golden/*` against it; remove `predictedRoute` from ground truth, fix the duplicated
   conflicting labels, remove `expectedLeadTimeDays`.
2. Add paraphrase diversity (templated variation, typos, code-mixed phrasing, long contacts), so
   distinct texts ≫ 69.
3. Add tenants (e.g. three synthetic business units), regions/brands per tenant, and synthetic users
   per role, so authorization is testable.
4. Add synthetic Component/Supplier/Batch/Plant graph data and seeded MCP-server data consistent with
   it.
5. Add synthetic PII into a labeled subset to test redaction.
6. Provide a `--scale N` mode (e.g. 1M rows, fixed seed) for load and ingestion throughput tests,
   written to `data/generated/` (gitignored).

---

## 23. Testing strategy

| Level | Scope | Infra |
|---|---|---|
| Unit | policy matrix, features/rules, RRF, MMR, context budgeting, numeric trace, citation membership, registry validation, gateway authz, cache-key construction, PII redaction | none; fakes for ports |
| Adapter contract tests | one shared test suite per port, run against every adapter (e.g. `VectorStore`: pgvector + in-memory) | testcontainers Postgres/Redis |
| Integration | migrations + RLS (cross-tenant queries return 0 rows), ingestion idempotency/replay, filtered ANN returns k, API end-to-end with FakeLLM and fake MCP servers, SSE stream | docker compose test profile |
| Eval | Section 22 | fixture DB |
| Security | authz matrix, injection set, header/CORS checks, dependency/container/secret scans | CI |
| Load (non-gating) | k6/Locust scenarios per route class; ingestion throughput with `--scale` | local compose |
| Frontend | Vitest unit, contract test against generated types, accessibility checks (axe) | existing |

---

## 24. Pluggable interfaces (ports)

Defined as `typing.Protocol`s in `backend/src/ccvie/core/ports.py`. The composition root
(`bootstrap/container.py`) chooses adapters from config; application code imports ports only.

```
EmbeddingModel     embed_documents(texts) / embed_query(text) / dimension / version
VectorStore        upsert(items) / search(vector, AccessFilter, MetadataFilter, k) / delete(ids)
KeywordIndex       search(query, AccessFilter, MetadataFilter, k)
GraphStore         resolve(entities) / subgraph(seeds, max_depth, edge_types, AccessFilter)
StructuredStore    run(operation: ApprovedOperation, AccessFilter) → FactEvidence
Reranker           rerank(query, candidates, top_n)
LLMClient          generate(...) / stream(...)
GroundednessChecker score(claim, evidence_texts) → entailment
ToolGateway        list_for(principal) / call(principal, ToolCall) / propose / confirm
Cache              get / set / delete_namespace
JobQueue           enqueue / consume / ack / dead_letter
PolicyEngine       access_filter(principal) / authorize(principal, capability)
```

Swap examples, all configuration-only: `VECTOR_STORE_BACKEND=pgvector|qdrant`,
`KEYWORD_BACKEND=pg_fts|pg_search|opensearch`, `EMBEDDING_BACKEND=local|remote`,
`LLM_PROVIDER=anthropic|openai_compatible|fake`, `RERANKER_BACKEND=cross_encoder|noop`.
Only the pgvector, pg_fts, local/remote embedding, cross-encoder/noop, Anthropic/OpenAI-compatible/
fake, Redis/in-memory adapters are implemented; the others are named to prove the seam, not built.

**Constraint:** changing the vector store also requires re-indexing and re-running the retrieval
eval. The port makes the change cheap in code, not free in operations.

---

## 25. API surface (FastAPI, `/v1`)

| Method | Path | Capability | Notes |
|---|---|---|---|
| POST | `/v1/query` | `query:ask` | JSON `QueryResponse` |
| POST | `/v1/query/stream` | `query:ask` | SSE events (Section 13) |
| GET | `/v1/insights` | `insights:read` | emerging issues, filtered by AccessFilter |
| GET | `/v1/insights/{id}` | `insights:read` | |
| GET | `/v1/verbatims?ids=` | `verbatims:read` | source text for citations, re-authorized |
| POST | `/v1/actions/{id}/confirm` | `actions:confirm` + tool scopes | executes a pending transactional call |
| POST | `/v1/actions/{id}/cancel` | `actions:confirm` | |
| GET | `/v1/tools` | `query:ask` | registry subset visible to the principal |
| POST | `/v1/feedback` | `feedback:write` | insight decisions and answer thumbs |
| POST | `/v1/ingest/batches` | `ingest:write` | 202 + run ID |
| POST | `/v1/ingest/events` | `ingest:write` | streaming contacts |
| GET | `/v1/ingest/batches/{id}` | `ingest:read` | run status |
| GET | `/healthz`, `/readyz`, `/metrics` | none / internal | |

All request/response models live in `contracts/` (Rule 1). New contract modules: `answer.py`
(`QueryResponse`, `Claim`, `SourceRef`, `Groundedness`, `AnswerState`, `Usage`), `router.py`
(`RoutingDecision`), `tools.py` (tool arg/result models, `PendingAction`), `auth.py`
(`PrincipalView` for the UI), `ingest.py`, `feedback.py`. The frontend regenerates types with
`npm run gen-types`.

---

## 26. Frontend integration (Next.js)

- **Pages:** existing feed and drill-down; new `/ask` (conversation with streaming answer), existing
  `/routing` page shows `RouteDecision.reasons` and class.
- **Citations:** claim text with inline citation chips; clicking opens the verbatim drawer, which
  loads source text from `/v1/verbatims` (never from the LLM). Fact and tool citations open a panel
  showing the query result or tool output.
- **Transparency:** route class badge, degraded-mode banner, groundedness indicator, "N claims
  removed — insufficient support" disclosure.
- **Human-in-the-loop:** pending actions render as a confirmation dialog (Radix `AlertDialog`,
  focus-trapped, labelled) showing exactly the arguments that will be sent.
- **Auth:** Next.js route handlers act as the BFF; session in httpOnly cookie; API called
  server-side with the bearer token.
- **Types:** generated only (`types.generated.ts`), CI drift check (existing rule).

---

## 27. Proposed project structure

Legend: `[E]` exists today, `[N]` new, `[M]` moved/renamed, `[X]` extended.

```
Consumer-Care-Verbatim-Insight-Engine/
├── .github/workflows/                      [N]
│   ├── ci.yml                              lint, type-check, unit+integration, types drift, model-name grep, scans
│   ├── eval-gate.yml                       deterministic eval metrics vs EVAL_* thresholds
│   └── nightly-eval.yml                    real-LLM judge metrics + fault injection (non-gating)
├── backend/
│   ├── pyproject.toml                      [X] declare real deps; entrypoints for api/workers
│   ├── Dockerfile                          [N] one image, entrypoint selects role
│   ├── src/ccvie/
│   │   ├── config.py                       [X] grouped settings (Section 30.3)
│   │   ├── contracts/                      [X] API shapes only (Rule 1)
│   │   │   ├── entities.py  insight.py  query.py            [E]
│   │   │   ├── router.py                   [X] QueryClass, RetrievalStrategy, RoutingDecision
│   │   │   ├── answer.py                   [N] QueryResponse, Claim, SourceRef, Groundedness, Usage
│   │   │   ├── tools.py                    [N] tool args/results, PendingAction
│   │   │   ├── planner.py                  [N] InvestigationPlan (from proposal)
│   │   │   ├── auth.py  ingest.py  feedback.py              [N]
│   │   ├── core/                           [N] internal (non-API) types and ports
│   │   │   ├── ports.py                    Protocols, Section 24
│   │   │   ├── models.py                   Evidence, AccessFilter, MetadataFilter, Principal
│   │   │   └── errors.py                   typed error hierarchy → HTTP mapping
│   │   ├── bootstrap/                      [N]
│   │   │   └── container.py                composition root: config → adapters
│   │   ├── api/                            [M] from retrieval_gen/api.py
│   │   │   ├── app.py                      app factory, middleware, lifespan
│   │   │   ├── deps.py                     auth, principal, policy dependencies
│   │   │   └── routes/ query.py insights.py verbatims.py actions.py tools.py ingest.py health.py
│   │   ├── security/                       [N]
│   │   │   ├── authn.py                    JWT/JWKS verification; dev issuer
│   │   │   ├── policy.py                   RBAC+ABAC → AccessFilter (pure)
│   │   │   └── rls.py                      per-transaction SET LOCAL helpers
│   │   ├── data_foundation/                [E] Layer 1
│   │   │   ├── db.py                       [E] pools (read/write), RLS session setup
│   │   │   ├── ingestion/                  [M] from ingestion.py
│   │   │   │   ├── sources.py  validate.py  normalize.py  pii.py  dedupe.py
│   │   │   │   ├── pipeline.py  watermarks.py  outbox.py
│   │   │   ├── detection.py                [N] (from proposal)
│   │   │   └── queries/                    [E] graph_queries.py vector_queries.py (+ sql_queries.py)
│   │   ├── router/                         [E] Layer 2
│   │   │   ├── features.py  rules.py  graph.py              [E]
│   │   │   ├── understand.py               [N] rewrite, scope check, entity resolution
│   │   │   ├── complexity.py  planner.py  plan_executor.py  [N] (from proposal)
│   │   ├── retrieval_gen/                  [E] Layer 3
│   │   │   ├── orchestrator.py             [E] LangGraph wiring of Section 4
│   │   │   ├── retrieval/                  [N] vector.py keyword.py graph.py structured.py fusion.py hybrid.py
│   │   │   ├── context.py                  [N] Section 12
│   │   │   ├── llm.py                      [E] thin facade over LLMClient port
│   │   │   ├── verification.py             [N] Section 14 checks
│   │   │   └── prompts/                    [E] versioned templates
│   │   ├── tools/                          [N] tool integration
│   │   │   ├── registry.yaml  registry.py  gateway.py  mcp_client.py  actions.py
│   │   ├── adapters/                       [N] implementations of ports
│   │   │   ├── vector/pgvector.py  keyword/pg_fts.py
│   │   │   ├── embeddings/local.py  embeddings/remote.py  embeddings/fake.py
│   │   │   ├── rerank/cross_encoder.py  rerank/noop.py
│   │   │   ├── llm/anthropic.py  llm/openai_compatible.py  llm/fake.py
│   │   │   ├── groundedness/nli.py  cache/redis.py  cache/memory.py  queue/redis.py
│   │   ├── observability/                  [N] logging.py tracing.py metrics.py cost.py
│   │   ├── workers/                        [N] entrypoints: ingest.py embed.py detector.py outbox_relay.py
│   │   └── evaluation/                     [E] Layer 5
│   │       ├── gate.py  lead_time.py  scoring.py  simulate.py   [E]
│   │       ├── runner.py  datasets.py                           [N]
│   │       └── metrics/ retrieval.py routing.py generation.py tools.py security.py   [N]
│   └── tests/
│       ├── unit/                           [X]
│       ├── contract/                       [N] shared adapter test suites
│       ├── integration/                    [X]
│       ├── eval/                           [X]
│       └── fakes/                          [N] fake MCP servers, FakeLLM scripts
├── mcp-servers/                            [N] synthetic enterprise systems, separate package
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── src/ccvie_enterprise_mock/
│       ├── common/ auth.py seed.py
│       ├── care_ops/server.py
│       ├── supply_chain/server.py
│       └── quality_cases/server.py
├── model-serving/                          [N] thin HTTP service for embed/rerank/NLI (optional in dev)
├── frontend/                               [E] Layer 4
│   └── src/app/ask/ …  src/app/api/ (BFF route handlers)  components/citation-*.tsx  action-confirm-dialog.tsx   [N]
├── db/
│   ├── migrations/                         [X] 0001… tenants/taxonomy, verbatims, embeddings, graph, RLS, ops tables
│   ├── seed/                               [X]
│   └── schema.sql                          [N] generated
├── data/
│   ├── consumer_care_verbatims_1000.csv    [E] vocabulary source
│   ├── generators/                         [X] Section 22.4
│   ├── golden/                             [X] rebuilt, Section 22.3
│   └── generated/                          [E] gitignored
├── deploy/                                 [N]
│   ├── otel-collector.yaml  prometheus.yml  grafana/ (dashboards)
├── docs/
│   ├── architecture.md                     [N] this document
│   └── adr/                                [N] 0004–0010, Section 29
├── docker-compose.yml                      [X] db, redis, api, workers, detector, models, mcp-*, otel, jaeger, prometheus, frontend
└── .env.example                            [X]
```

---

## 28. Key design decisions and trade-offs

| # | Decision | Why | Cost / what we give up | Revisit when |
|---|---|---|---|---|
| D1 | Postgres is the single store for verbatims, vectors, FTS, graph, aggregates, audit | One consistency model, one backup, RLS covers everything, joins across vector/graph/metadata in one query | Not the best-in-class engine for any single workload; vector QPS ceiling | >50–100M vectors, ANN p95 over budget, or FTS relevance gap in ablation |
| D2 | Postgres FTS as "keyword/BM25" retriever | No extra service; fine for short texts | Not true BM25 | Ablation shows keyword recall gap → `pg_search`/OpenSearch adapter |
| D3 | Deterministic-first routing, LLM planner only for complex/low confidence | Cheap, fast, reproducible, testable | Rules need maintenance; long-tail phrasing depends on planner | Routing accuracy plateaus below threshold on rules |
| D4 | HYBRID derived from plan, not predicted | Removes classifier disagreement; class follows from what actually executes | Class label is only known after planning | — |
| D5 | Authorization in four layers (policy, typed ports, RLS, post-filter) | A single missed `WHERE` cannot leak data; LLM has no role | More code and per-transaction `SET LOCAL` overhead (small) | — |
| D6 | Filters inside ANN (iterative scan / partition / exact fallback) | Correct top-k under selective filters | Tuning; slightly slower than unfiltered ANN | — |
| D7 | MCP behind an internal Tool Gateway with a registry | Standard tool protocol + central authz, schema pinning, confirmation | Extra hop and protocol surface | A tool's latency budget cannot absorb the hop → direct adapter |
| D8 | Transactional tools require explicit human confirmation | Actions on enterprise systems must be attributable to a person | One extra click; no fully autonomous actions | Low-risk actions with an explicit policy exemption |
| D9 | Structured JSON generation, then verify, then render | Enables per-claim citation, numeric, and NLI checks; prose cannot smuggle claims | Less fluent prose; schema failures need repair | — |
| D10 | NLI groundedness online, LLM judge offline | Local, cheap, deterministic in the hot path | NLI misses some paraphrase support; threshold needs calibration | Judge/NLI disagreement high on answer set |
| D11 | Redis added for cache, queue, rate limits, breaker state | Standard, simple; shared state across API replicas | One more service (the proposal preferred none) | Could fall back to Postgres queue + in-process cache for a minimal deployment |
| D12 | No semantic cache | Wrong-scope answers are worse than slow answers | Fewer cache hits | Eval shows safe threshold |
| D13 | One codebase, several entrypoints/containers | Independent scaling without microservice overhead | Shared deploy cadence; dependency set is shared | A component needs a different release cadence or language |
| D14 | Model serving as a separate service | API replicas stay small; GPU placement independent | Network hop on the hot path (~5–20 ms) | Dev mode runs models in-process |
| D15 | Citation handles are opaque; DB IDs never enter the prompt | LLM cannot fabricate a plausible source ID | Mapping bookkeeping | — |
| D16 | Verbatim text in UI always fetched by ID from the DB | A hallucinated quote cannot be displayed | Extra request per drill-down | — |
| D17 | Local GraphRAG only | Questions are entity-centric; global summarization is costly | No corpus-wide community themes | Thematic eval shows a gap vector+facets cannot close |

---

## 29. Conflicts with the existing plan and required ADRs

The proposal states that any change needs an ADR. These are the changes this design makes; each
needs an ADR (numbering continues after the proposal's planned 0001–0003) and your approval.

| ADR | Change | Conflicts with |
|---|---|---|
| 0004 | Adopt MCP via Tool Gateway + registry; implement 3 synthetic servers | Proposal §10 ("Do not add MCP…") and §18 (MCP is COULD/FUTURE) |
| 0005 | Four-class `query_class` (KNOWLEDGE/REAL_TIME_DATA/TRANSACTIONAL/HYBRID) alongside retrieval strategies; `RouteDecision` contract change | `contracts/router.py` (graph/vector only); router golden set shape |
| 0006 | Multi-tenant RBAC/ABAC, Postgres RLS, JWT auth, BFF | Not covered by proposal; affects every table and the CSV schema |
| 0007 | Ports-and-adapters layout (`core/`, `adapters/`, `bootstrap/`), `api/` moved out of `retrieval_gen/` | Proposal §3 folder tree; `CLAUDE.md` uvicorn command path |
| 0008 | Redis for cache/queue/rate-limit | Proposal's single-store preference |
| 0009 | Cross-encoder reranking promoted from SHOULD to MUST (with no-op fallback) | Proposal §5/§18 |
| 0010 | Separate model-serving and MCP containers; production-style compose topology | Proposal §2 "local Docker only" — still local Docker, but more services |

Also to correct during implementation: `CLAUDE.md` calls the entity model a "shallow hierarchy"
while the proposal defines a deep ontology; it mentions a `packages/` directory that does not
exist; the golden-set issues in Section 2.

---

## 30. Delivery plan, configuration, open questions

### 30.1 Phases (after approval)

1. **Skeleton:** structure, ports, config, contracts, migrations with RLS, compose topology, CI
   workflows, fakes. Exit: `/readyz` green, RLS cross-tenant test passes, types generated.
2. **Ingestion + knowledge path:** generator, ingestion pipeline, embeddings + cache, hybrid
   retrieval + rerank, context, generation, verification, `/v1/query`. Exit: retrieval and answer
   evals running in CI with FakeLLM.
3. **Routing + tools:** features/rules, planner, registry, gateway, 3 MCP servers, pending actions.
   Exit: routing and tool evals + authz matrix gating.
4. **Detection + UI:** detection job, insights API, `/ask` page, citations, confirmation dialog, BFF
   auth. Exit: end-to-end demo on the South/Leakage planted issue.
5. **Hardening:** observability dashboards, degradation tests, load tests, nightly judge eval,
   runbook.

### 30.2 Explicitly deferred

Global GraphRAG, semantic cache, dedicated vector/graph engines, fully autonomous actions,
cloud-specific IaC, streaming-platform (Kafka) adapter implementation.

### 30.3 New configuration keys (names only; values in `.env.example` after approval)

```
# Security:      AUTH_ISSUER AUTH_AUDIENCE AUTH_JWKS_URL AUTH_DEV_MODE RATE_LIMIT_USER_PER_MIN
#                RATE_LIMIT_TENANT_PER_MIN TENANT_DAILY_TOKEN_BUDGET MAX_QUERY_CHARS
# Database:      DATABASE_READ_URL DB_POOL_MIN DB_POOL_MAX
# Embeddings:    EMBEDDING_BACKEND EMBEDDING_DIMENSION ACTIVE_EMBEDDING_VERSION EMBED_BATCH_SIZE
#                MODEL_SERVING_URL
# Retrieval:     VECTOR_STORE_BACKEND KEYWORD_BACKEND RETRIEVAL_VECTOR_CANDIDATES
#                RETRIEVAL_KEYWORD_CANDIDATES RETRIEVAL_GRAPH_CANDIDATES RRF_K RRF_WEIGHTS
#                RERANKER_BACKEND RERANKER_MODEL_NAME RERANK_CANDIDATES DEDUP_COSINE_MIN
#                VECTOR_EXACT_SCAN_MAX_ROWS HNSW_EF_SEARCH GRAPH_CONTEXT_MAX_EDGES
# Context/LLM:   CONTEXT_BUDGET_TOKENS CONTEXT_SHARE_FACTS CONTEXT_SHARE_VERBATIMS CONTEXT_SHARE_TOOLS
#                LLM_PLANNER_MODEL_NAME LLM_JUDGE_MODEL_NAME LLM_FALLBACK_PROVIDER LLM_TIMEOUT_MS
#                LLM_PRICE_TABLE GENERATION_SKIP_FOR_STRUCTURED
# Verification:  GROUNDEDNESS_BACKEND GROUNDEDNESS_MODEL_NAME GROUNDEDNESS_MIN_ENTAILMENT
#                GROUNDEDNESS_MAX_DROPPED_RATIO VERIFY_FAIL_MODE
# Tools:         TOOL_REGISTRY_PATH MCP_SERVER_URLS TOOL_OUTPUT_MAX_BYTES PENDING_ACTION_TTL_S
# Cache/queue:   REDIS_URL CACHE_RETRIEVAL_TTL_S CACHE_LLM_TTL_S QUEUE_BACKEND INGEST_MAX_QUEUE_DEPTH
# Resilience:    REQUEST_DEADLINE_MS BREAKER_FAILURE_THRESHOLD BREAKER_RESET_S
# Ingestion:     CHUNK_MAX_TOKENS CHUNK_OVERLAP_TOKENS
# Observability: OTEL_EXPORTER_OTLP_ENDPOINT LOG_LEVEL LOG_PROMPTS METRICS_ENABLED
# Eval:          EVAL_RECALL_AT_20_MIN EVAL_MRR_MIN EVAL_PRECISION_AT_5_MIN EVAL_ROUTING_ACCURACY_MIN
#                EVAL_TOOL_SUCCESS_MIN EVAL_FAITHFULNESS_MIN EVAL_CITATION_PRECISION_MIN
#                EVAL_NUMERIC_ACCURACY_MIN EVAL_LEAK_RATE_MAX EVAL_INJECTION_SUCCESS_MAX
```

### 30.4 Resolved decisions (2026-09-28)

1. MCP adopted behind the Tool Gateway (ADR-0004).
2. Redis added (ADR-0008).
3. Keyword retriever starts as Postgres FTS (ADR-0009).
4. `data/golden/` is rebuilt on the CSV vocabulary (Section 22.4).
5. Model serving runs in-process by default; remote adapter when needed (ADR-0010).
