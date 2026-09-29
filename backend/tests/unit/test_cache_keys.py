from uuid import uuid4

from ccvie.core.cache_keys import scoped_cache_key
from ccvie.core.models import AccessFilter, Classification

TENANT = uuid4()


def access(regions: set[str] | None) -> AccessFilter:
    return AccessFilter(
        tenant_id=TENANT,
        regions=frozenset(regions) if regions is not None else None,
        brands=None,
        max_classification=Classification.RESTRICTED,
    )


def test_same_scope_and_parts_share_a_key() -> None:
    parts = {"q": "leaking bottle", "k": 10}
    assert scoped_cache_key("retrieval", access({"south", "north"}), parts) == scoped_cache_key(
        "retrieval", access({"north", "south"}), dict(reversed(parts.items()))
    )


def test_different_scopes_never_share_a_key() -> None:
    parts = {"q": "leaking bottle"}
    keys = {
        scoped_cache_key("retrieval", access({"south"}), parts),
        scoped_cache_key("retrieval", access({"north"}), parts),
        scoped_cache_key("retrieval", access(None), parts),
        scoped_cache_key("retrieval", access(set()), parts),
    }
    assert len(keys) == 4


def test_restricted_and_internal_clearance_differ() -> None:
    internal = AccessFilter(
        tenant_id=TENANT, regions=None, brands=None, max_classification=Classification.INTERNAL
    )
    assert scoped_cache_key("llm", internal, {}) != scoped_cache_key("llm", access(None), {})
