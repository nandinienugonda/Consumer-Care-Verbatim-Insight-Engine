"""Row-Level Security holds even when a query has no tenant predicate."""

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg
import pytest

from ccvie.config import Settings, settings
from ccvie.data_foundation.db import Database, DbRole
from ccvie.data_foundation.migrate import apply_migrations

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

SUFFIX = uuid4().hex[:8]
BRAND, CATEGORY, PRODUCT, PACK = (f"t-{name}-{SUFFIX}" for name in ("brand", "cat", "prod", "pack"))
COUNTRY, REGION, CHANNEL = (f"t-{name}-{SUFFIX}" for name in ("country", "region", "channel"))


async def _owner(require_db: bool) -> asyncpg.Connection:
    try:
        return await asyncpg.connect(settings.database_url, timeout=3)
    except (OSError, asyncpg.PostgresError) as exc:
        message = f"PostgreSQL not reachable: {type(exc).__name__}"
        if require_db:
            pytest.fail(message)
        pytest.skip(message)


async def _seed(conn: asyncpg.Connection) -> tuple[UUID, UUID]:
    await conn.execute("INSERT INTO brands VALUES ($1, $1)", BRAND)
    await conn.execute("INSERT INTO categories VALUES ($1, $1)", CATEGORY)
    await conn.execute("INSERT INTO products VALUES ($1, $1, $2, $3)", PRODUCT, BRAND, CATEGORY)
    await conn.execute(
        "INSERT INTO packs (code, name, product_code, version) VALUES ($1, $1, $2, 'new')",
        PACK,
        PRODUCT,
    )
    await conn.execute("INSERT INTO countries VALUES ($1, $1)", COUNTRY)
    await conn.execute("INSERT INTO regions VALUES ($1, $1, $2)", REGION, COUNTRY)
    await conn.execute("INSERT INTO channels VALUES ($1, $1)", CHANNEL)
    tenants = []
    for label in ("a", "b"):
        tenant = await conn.fetchval(
            "INSERT INTO tenants (name) VALUES ($1) RETURNING id", f"t-{label}-{SUFFIX}"
        )
        text = f"bottle leaks in tenant {label}"
        await conn.execute(
            """
            INSERT INTO verbatims (tenant_id, source_system, contact_id, occurred_at, product_code,
                pack_code, brand_code, region_code, channel_code, text_redacted, content_sha256,
                source_updated_at)
            VALUES ($1, 'test', $2, $3, $4, $5, $6, $7, $8, $9, $10, $3)
            """,
            tenant,
            f"c-{label}",
            datetime.now(UTC),
            PRODUCT,
            PACK,
            BRAND,
            REGION,
            CHANNEL,
            text,
            hashlib.sha256(text.encode()).hexdigest(),
        )
        tenants.append(tenant)
    return tenants[0], tenants[1]


async def _cleanup(conn: asyncpg.Connection, tenants: tuple[UUID, UUID]) -> None:
    await conn.execute("DELETE FROM verbatims WHERE tenant_id = ANY($1)", list(tenants))
    await conn.execute("DELETE FROM tenants WHERE id = ANY($1)", list(tenants))
    for table, code in (
        ("packs", PACK),
        ("products", PRODUCT),
        ("brands", BRAND),
        ("categories", CATEGORY),
        ("regions", REGION),
        ("countries", COUNTRY),
        ("channels", CHANNEL),
    ):
        await conn.execute(f"DELETE FROM {table} WHERE code = $1", code)  # noqa: S608


@pytest.fixture
async def seeded(require_db: bool) -> AsyncIterator[tuple[Database, UUID, UUID]]:
    owner = await _owner(require_db)
    await apply_migrations(settings.database_url, settings.migrations_dir)
    tenants = await _seed(owner)
    db = Database(Settings(_env_file=None, database_url=settings.database_url))
    await db.connect()
    try:
        yield db, *tenants
    finally:
        await db.close()
        await _cleanup(owner, tenants)
        await owner.close()


async def test_each_tenant_sees_only_its_rows(seeded: tuple[Database, UUID, UUID]) -> None:
    db, tenant_a, tenant_b = seeded
    for tenant in (tenant_a, tenant_b):
        async with db.scoped(tenant, DbRole.QUERY) as conn:
            rows = await conn.fetch("SELECT tenant_id FROM verbatims")
            assert {row["tenant_id"] for row in rows} == {tenant}
            assert await conn.fetchval("SELECT count(*) FROM tenants") == 1


async def test_unknown_tenant_sees_nothing(seeded: tuple[Database, UUID, UUID]) -> None:
    db, _, _ = seeded
    async with db.scoped(uuid4(), DbRole.QUERY) as conn:
        assert await conn.fetchval("SELECT count(*) FROM verbatims") == 0


async def test_unset_tenant_sees_nothing(seeded: tuple[Database, UUID, UUID]) -> None:
    db, _, _ = seeded
    async with db._pool(readonly=True).acquire() as conn, conn.transaction():
        await conn.execute(f"SET LOCAL ROLE {DbRole.QUERY.value}")
        assert await conn.fetchval("SELECT count(*) FROM verbatims") == 0


async def test_query_role_cannot_write_verbatims(seeded: tuple[Database, UUID, UUID]) -> None:
    db, tenant_a, _ = seeded
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with db.scoped(tenant_a, DbRole.QUERY, readonly=False) as conn:
            await conn.execute("DELETE FROM verbatims")


async def test_ingest_role_cannot_write_into_another_tenant(
    seeded: tuple[Database, UUID, UUID],
) -> None:
    db, tenant_a, tenant_b = seeded
    async with db.scoped(tenant_a, DbRole.INGEST, readonly=False) as conn:
        updated = await conn.execute(
            "UPDATE verbatims SET text_redacted = 'x' WHERE tenant_id = $1", tenant_b
        )
        assert updated == "UPDATE 0"
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        async with db.scoped(tenant_a, DbRole.INGEST, readonly=False) as conn:
            await conn.execute(
                "UPDATE verbatims SET tenant_id = $1 WHERE tenant_id = $2", tenant_b, tenant_a
            )


async def test_embedding_dimension_matches_config(seeded: tuple[Database, UUID, UUID]) -> None:
    db, _, _ = seeded
    assert await db.embedding_dimension() == settings.embedding_dimension
