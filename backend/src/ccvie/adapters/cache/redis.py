from redis.asyncio import Redis


class RedisCache:
    def __init__(self, url: str) -> None:
        self._client = Redis.from_url(url)

    async def get(self, key: str) -> bytes | None:
        return await self._client.get(key)

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        await self._client.set(key, value, ex=ttl_s)

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def close(self) -> None:
        await self._client.aclose()
