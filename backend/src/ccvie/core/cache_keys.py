import hashlib
import json

from ccvie.core.models import AccessFilter


def scoped_cache_key(namespace: str, access: AccessFilter, parts: dict[str, object]) -> str:
    """Every cache key is bound to the caller's AccessFilter so no entry is shared across
    principals with different data scopes."""
    payload = json.dumps(parts, sort_keys=True, default=str).encode()
    return f"ccvie:{namespace}:{access.fingerprint()}:{hashlib.sha256(payload).hexdigest()}"
