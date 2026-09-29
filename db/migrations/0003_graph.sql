-- PostgreSQL-based property graph model with relational tables and SQL joins,
-- with GraphRAG-style retrieval.
CREATE TABLE graph_nodes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants,
    label text NOT NULL,
    key text NOT NULL,
    props jsonb NOT NULL DEFAULT '{}',
    UNIQUE (tenant_id, label, key),
    UNIQUE (id, tenant_id)
);

CREATE TABLE graph_edges (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id uuid NOT NULL,
    type text NOT NULL,
    src uuid NOT NULL,
    dst uuid NOT NULL,
    props jsonb NOT NULL DEFAULT '{}',
    UNIQUE (tenant_id, type, src, dst),
    -- Composite keys make a cross-tenant edge impossible.
    FOREIGN KEY (src, tenant_id) REFERENCES graph_nodes (id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (dst, tenant_id) REFERENCES graph_nodes (id, tenant_id) ON DELETE CASCADE
);

-- Postgres does not index foreign-key columns automatically; multi-hop traversal needs both.
CREATE INDEX graph_edges_src ON graph_edges (src);
CREATE INDEX graph_edges_dst ON graph_edges (dst);
