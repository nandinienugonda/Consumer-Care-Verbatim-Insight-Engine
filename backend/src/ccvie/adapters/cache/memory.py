import time


class MemoryCache:
    """Single-process cache for tests and local runs without Redis."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, bytes]] = {}

    async def get(self, key: str) -> bytes | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return value

    async def set(self, key: str, value: bytes, ttl_s: int) -> None:
        self._entries[key] = (time.monotonic() + ttl_s, value)

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._entries.clear()
