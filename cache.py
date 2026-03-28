import time
from typing import Optional


class TTLCache:
    """Simple in-memory key-value store with per-entry TTL expiry."""

    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}
        self._start_time = time.time()

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl: int = 300):
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str):
        self._store.pop(key, None)

    def purge_expired(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)


cache = TTLCache()
