"""Apply db/migrations/*.sql in order. Applied files are immutable: a changed checksum fails."""

import asyncio
import hashlib
import re
from pathlib import Path

import asyncpg

from ccvie.config import settings

MIGRATION_NAME = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
LOCK_KEY = 7_302_026


def migration_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if MIGRATION_NAME.match(path.name))


async def apply_migrations(dsn: str, directory: Path) -> list[str]:
    conn = await asyncpg.connect(dsn)
    applied_now: list[str] = []
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", LOCK_KEY)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        applied = {
            row["version"]: row["checksum"]
            for row in await conn.fetch("SELECT version, checksum FROM schema_migrations")
        }
        for path in migration_files(directory):
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if path.stem in applied:
                if applied[path.stem] != checksum:
                    raise RuntimeError(f"{path.name} changed after it was applied")
                continue
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES ($1, $2)",
                    path.stem,
                    checksum,
                )
            applied_now.append(path.stem)
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)
        await conn.close()
    return applied_now


def main() -> None:
    applied = asyncio.run(apply_migrations(settings.database_url, settings.migrations_dir))
    print("applied:", ", ".join(applied) if applied else "nothing (up to date)")


if __name__ == "__main__":
    main()
