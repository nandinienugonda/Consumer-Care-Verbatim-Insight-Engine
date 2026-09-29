CREATE TABLE audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL,
    tenant_id uuid NOT NULL REFERENCES tenants,
    principal_id text NOT NULL,
    operation text NOT NULL,
    routing jsonb,
    parameters jsonb NOT NULL DEFAULT '{}',
    source_ids uuid[] NOT NULL DEFAULT '{}',
    tools_called text[] NOT NULL DEFAULT '{}',
    row_count integer,
    latency_ms double precision,
    cost_usd numeric(12, 6),
    verification jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_log_tenant_time ON audit_log (tenant_id, created_at DESC);
