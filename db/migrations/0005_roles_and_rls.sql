-- Application code runs every tenant transaction as one of these roles (SET LOCAL ROLE).
-- In production, grant them to a non-superuser login: GRANT ccvie_query TO <app_login>;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ccvie_query') THEN
        CREATE ROLE ccvie_query NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ccvie_ingest') THEN
        CREATE ROLE ccvie_ingest NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO ccvie_query, ccvie_ingest;

GRANT SELECT ON tenants, brands, categories, products, packs, countries, regions, channels,
    issue_categories, issue_types, taxonomy_aliases
    TO ccvie_query, ccvie_ingest;

GRANT SELECT ON verbatims, verbatim_embeddings, graph_nodes, graph_edges, embedding_cache
    TO ccvie_query;
GRANT SELECT, INSERT, UPDATE, DELETE ON verbatims, verbatim_embeddings, graph_nodes, graph_edges
    TO ccvie_ingest;
GRANT SELECT, INSERT ON embedding_cache TO ccvie_ingest;
GRANT INSERT ON audit_log TO ccvie_query, ccvie_ingest;

-- Unset or empty app.tenant_id yields NULL, which matches no row: deny by default.
CREATE FUNCTION app_tenant_id() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid $$;

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants USING (id = app_tenant_id());

ALTER TABLE verbatims ENABLE ROW LEVEL SECURITY;
ALTER TABLE verbatims FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON verbatims
    USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id());

ALTER TABLE verbatim_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE verbatim_embeddings FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON verbatim_embeddings
    USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id());

ALTER TABLE graph_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_nodes FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON graph_nodes
    USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id());

ALTER TABLE graph_edges ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edges FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON graph_edges
    USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id());

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit_log
    USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id = app_tenant_id());
