"""asyncpg pools and tenant-scoped transactions.

Every transaction that touches tenant data goes through Database.scoped(), which switches to a
non-privileged role and sets app.tenant_id so Postgres Row-Level Security applies even if a query
forgets its tenant predicate."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from uuid import UUID

import asyncpg

from ccvie.config import Settings


class DbRole(StrEnum):
    QUERY = "ccvie_query"
    INGEST = "ccvie_ingest"


class Database:
    def __init__(self, settings: Settings) -> None:
        self._write_dsn = settings.database_url
        self._read_dsn = settings.database_read_url
        self._min = settings.db_pool_min
        self._max = settings.db_pool_max
        self._write: asyncpg.Pool | None = None
        self._read: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._write = await asyncpg.create_pool(
            self._write_dsn, min_size=self._min, max_size=self._max
        )
        self._read = (
            await asyncpg.create_pool(self._read_dsn, min_size=self._min, max_size=self._max)
            if self._read_dsn
            else self._write
        )

    async def close(self) -> None:
        if self._read is not None and self._read is not self._write:
            await self._read.close()
        if self._write is not None:
            await self._write.close()

    def _pool(self, readonly: bool) -> asyncpg.Pool:
        pool = self._read if readonly else self._write
        if pool is None:
            raise RuntimeError("Database.connect() has not been awaited")
        return pool

    @asynccontextmanager
    async def scoped(
        self, tenant_id: UUID, role: DbRole, *, readonly: bool = True
    ) -> AsyncIterator[asyncpg.Connection]:
        async with self._pool(readonly).acquire() as conn, conn.transaction(readonly=readonly):
            # role is a closed enum, so interpolating it is safe; SET ROLE takes no parameters.
            await conn.execute(f"SET LOCAL ROLE {role.value}")
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", str(tenant_id))
            yield conn

    async def ping(self) -> bool:
        async with self._pool(readonly=True).acquire() as conn:
            return await conn.fetchval("SELECT 1") == 1

    async def applied_migrations(self) -> set[str]:
        async with self._pool(readonly=True).acquire() as conn:
            if await conn.fetchval("SELECT to_regclass('schema_migrations')") is None:
                return set()
            rows = await conn.fetch("SELECT version FROM schema_migrations")
            return {row["version"] for row in rows}

    async def embedding_dimension(self) -> int | None:
        async with self._pool(readonly=True).acquire() as conn:
            return await conn.fetchval(
                """
                SELECT atttypmod FROM pg_attribute
                WHERE attrelid = to_regclass('verbatim_embeddings') AND attname = 'embedding'
                """
            )
