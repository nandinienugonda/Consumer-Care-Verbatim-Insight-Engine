CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Reference taxonomy is shared by all tenants. Codes are stable slugs (e.g. 'freshglow', 'south').
CREATE TABLE brands (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE categories (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE products (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    brand_code text NOT NULL REFERENCES brands,
    category_code text NOT NULL REFERENCES categories,
    UNIQUE (code, brand_code)
);

CREATE TABLE packs (
    code text PRIMARY KEY,
    name text NOT NULL,
    product_code text NOT NULL REFERENCES products,
    version text NOT NULL CHECK (version IN ('standard', 'new')),
    replaced_by text REFERENCES packs,
    UNIQUE (product_code, name, version),
    UNIQUE (code, product_code)
);

CREATE TABLE countries (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE regions (
    code text PRIMARY KEY,
    name text NOT NULL,
    country_code text NOT NULL REFERENCES countries,
    UNIQUE (country_code, name)
);

CREATE TABLE channels (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE issue_categories (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE issue_types (
    code text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    category_code text NOT NULL REFERENCES issue_categories
);

CREATE TABLE taxonomy_aliases (
    entity_kind text NOT NULL
        CHECK (entity_kind IN ('brand', 'product', 'pack', 'region', 'issue_type', 'channel')),
    alias text NOT NULL,
    entity_code text NOT NULL,
    PRIMARY KEY (entity_kind, alias)
);

CREATE INDEX taxonomy_aliases_alias_trgm ON taxonomy_aliases USING gin (alias gin_trgm_ops);
