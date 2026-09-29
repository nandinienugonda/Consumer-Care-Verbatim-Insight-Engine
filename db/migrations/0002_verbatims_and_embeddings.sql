CREATE TABLE verbatims (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants,
    source_system text NOT NULL,
    contact_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    product_code text NOT NULL,
    pack_code text NOT NULL,
    brand_code text NOT NULL,
    region_code text NOT NULL REFERENCES regions,
    channel_code text NOT NULL REFERENCES channels,
    issue_type_code text REFERENCES issue_types,
    sentiment text CHECK (sentiment IN ('negative', 'neutral', 'positive')),
    classification text NOT NULL DEFAULT 'restricted'
        CHECK (classification IN ('internal', 'restricted')),
    text_redacted text NOT NULL,
    content_sha256 text NOT NULL,
    source_updated_at timestamptz NOT NULL,
    fts tsvector GENERATED ALWAYS AS (to_tsvector('english', text_redacted)) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, source_system, contact_id),
    UNIQUE (id, tenant_id),
    -- brand_code is denormalized for filtered retrieval; these keys keep it consistent.
    FOREIGN KEY (product_code, brand_code) REFERENCES products (code, brand_code),
    FOREIGN KEY (pack_code, product_code) REFERENCES packs (code, product_code)
);

CREATE INDEX verbatims_fts ON verbatims USING gin (fts);
CREATE INDEX verbatims_tenant_time ON verbatims (tenant_id, occurred_at DESC);
CREATE INDEX verbatims_tenant_scope ON verbatims (tenant_id, region_code, brand_code);

-- vector(384) must equal EMBEDDING_DIMENSION; /readyz fails when they differ.
CREATE TABLE verbatim_embeddings (
    verbatim_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    embedding_version text NOT NULL,
    region_code text NOT NULL,
    brand_code text NOT NULL,
    classification text NOT NULL,
    occurred_at timestamptz NOT NULL,
    embedding vector(384) NOT NULL,
    PRIMARY KEY (verbatim_id, embedding_version),
    FOREIGN KEY (verbatim_id, tenant_id) REFERENCES verbatims (id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX verbatim_embeddings_hnsw ON verbatim_embeddings
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX verbatim_embeddings_tenant_version
    ON verbatim_embeddings (tenant_id, embedding_version);

-- Keyed by the hash of normalized, redacted text; stores no text.
CREATE TABLE embedding_cache (
    model_name text NOT NULL,
    embedding_version text NOT NULL,
    content_sha256 text NOT NULL,
    embedding vector(384) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, embedding_version, content_sha256)
);
