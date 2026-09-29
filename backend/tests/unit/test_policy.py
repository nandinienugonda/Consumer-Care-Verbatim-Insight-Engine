from uuid import uuid4

import pytest

from ccvie.core.errors import Forbidden
from ccvie.core.models import AccessFilter, Classification, Principal, Role
from ccvie.security.policy import Capability, access_filter, authorize

TENANT = uuid4()


def principal(*roles: Role, regions: set[str] | None = None) -> Principal:
    return Principal(
        user_id="u1",
        tenant_id=TENANT,
        roles=frozenset(roles),
        regions=frozenset(regions) if regions is not None else None,
    )


@pytest.mark.parametrize(
    ("role", "capability", "allowed"),
    [
        (Role.CARE_ANALYST, Capability.QUERY_ASK, True),
        (Role.CARE_ANALYST, Capability.VERBATIMS_READ, True),
        (Role.CARE_ANALYST, Capability.ACTIONS_CONFIRM, False),
        (Role.QUALITY_MANAGER, Capability.ACTIONS_CONFIRM, True),
        (Role.EXECUTIVE, Capability.QUERY_ASK, True),
        (Role.EXECUTIVE, Capability.VERBATIMS_READ, False),
        (Role.INGEST_SERVICE, Capability.QUERY_ASK, False),
        (Role.INGEST_SERVICE, Capability.INGEST_WRITE, True),
        (Role.PLATFORM_ADMIN, Capability.VERBATIMS_READ, False),
    ],
)
def test_capability_matrix(role: Role, capability: Capability, allowed: bool) -> None:
    if allowed:
        authorize(principal(role), capability)
    else:
        with pytest.raises(Forbidden):
            authorize(principal(role), capability)


def test_no_roles_means_no_capabilities() -> None:
    with pytest.raises(Forbidden):
        authorize(principal(), Capability.QUERY_ASK)


def test_analyst_filter_is_tenant_bound_and_restricted() -> None:
    access = access_filter(principal(Role.CARE_ANALYST, regions={"south"}))
    assert access.tenant_id == TENANT
    assert access.regions == frozenset({"south"})
    assert access.max_classification is Classification.RESTRICTED


def test_executive_cannot_see_restricted_text() -> None:
    assert access_filter(principal(Role.EXECUTIVE)).max_classification is Classification.INTERNAL


def test_highest_clearance_across_roles_wins() -> None:
    access = access_filter(principal(Role.EXECUTIVE, Role.CARE_ANALYST))
    assert access.max_classification is Classification.RESTRICTED


@pytest.mark.parametrize("role", [Role.INGEST_SERVICE, Role.PLATFORM_ADMIN])
def test_non_data_roles_get_no_filter(role: Role) -> None:
    with pytest.raises(Forbidden):
        access_filter(principal(role))


def test_regional_manager_requires_regions_claim() -> None:
    with pytest.raises(Forbidden):
        access_filter(principal(Role.REGIONAL_MANAGER))
    assert access_filter(principal(Role.REGIONAL_MANAGER, regions={"north"})).regions == {"north"}


def test_allows_checks_every_dimension() -> None:
    access = AccessFilter(
        tenant_id=TENANT,
        regions=frozenset({"south"}),
        brands=frozenset({"freshglow"}),
        max_classification=Classification.INTERNAL,
    )
    ok = {
        "tenant_id": TENANT,
        "region": "south",
        "brand": "freshglow",
        "classification": Classification.INTERNAL,
    }
    assert access.allows(**ok)
    assert not access.allows(**{**ok, "tenant_id": uuid4()})
    assert not access.allows(**{**ok, "region": "north"})
    assert not access.allows(**{**ok, "brand": "purewash"})
    assert not access.allows(**{**ok, "classification": Classification.RESTRICTED})
    assert not access.allows(**{**ok, "region": None})
