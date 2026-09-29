"""Composition root: the only module that chooses adapters."""

from dataclasses import dataclass

from ccvie.adapters.cache.redis import RedisCache
from ccvie.config import Settings
from ccvie.core.ports import Cache
from ccvie.data_foundation.db import Database
from ccvie.security.authn import TokenVerifier


@dataclass
class Container:
    settings: Settings
    db: Database
    cache: Cache
    verifier: TokenVerifier

    async def close(self) -> None:
        await self.cache.close()
        await self.db.close()


async def build_container(settings: Settings) -> Container:
    verifier = TokenVerifier(settings)
    db = Database(settings)
    await db.connect()
    return Container(
        settings=settings, db=db, cache=RedisCache(settings.redis_url), verifier=verifier
    )
