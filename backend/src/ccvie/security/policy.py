"""RBAC for capabilities, ABAC for data scope. Pure functions, deny by default."""

from enum import StrEnum

from ccvie.core.errors import Forbidden
from ccvie.core.models import AccessFilter, Classification, Principal, Role


class Capability(StrEnum):
    QUERY_ASK = "query:ask"
    INSIGHTS_READ = "insights:read"
    VERBATIMS_READ = "verbatims:read"
    ACTIONS_CONFIRM = "actions:confirm"
    FEEDBACK_WRITE = "feedback:write"
    INGEST_WRITE = "ingest:write"
    INGEST_READ = "ingest:read"
    TOOLS_ADMIN = "tools:admin"


_ANALYST = frozenset(
    {
        Capability.QUERY_ASK,
        Capability.INSIGHTS_READ,
        Capability.VERBATIMS_READ,
        Capability.FEEDBACK_WRITE,
    }
)

ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.CARE_ANALYST: _ANALYST,
    Role.QUALITY_MANAGER: _ANALYST | {Capability.ACTIONS_CONFIRM},
    Role.REGIONAL_MANAGER: _ANALYST,
    Role.EXECUTIVE: frozenset({Capability.QUERY_ASK, Capability.INSIGHTS_READ}),
    Role.INGEST_SERVICE: frozenset({Capability.INGEST_WRITE, Capability.INGEST_READ}),
    Role.PLATFORM_ADMIN: frozenset({Capability.TOOLS_ADMIN, Capability.INGEST_READ}),
}

# Roles absent from this map cannot read tenant data at all.
ROLE_CLEARANCE: dict[Role, Classification] = {
    Role.CARE_ANALYST: Classification.RESTRICTED,
    Role.QUALITY_MANAGER: Classification.RESTRICTED,
    Role.REGIONAL_MANAGER: Classification.RESTRICTED,
    Role.EXECUTIVE: Classification.INTERNAL,
}

# A token for these roles must carry an explicit regions claim.
ROLES_REQUIRING_REGION_SCOPE = frozenset({Role.REGIONAL_MANAGER})


def capabilities(principal: Principal) -> frozenset[Capability]:
    granted: frozenset[Capability] = frozenset()
    for role in principal.roles:
        granted |= ROLE_CAPABILITIES.get(role, frozenset())
    return granted


def authorize(principal: Principal, capability: Capability) -> None:
    if capability not in capabilities(principal):
        raise Forbidden(f"missing capability {capability.value}")


def access_filter(principal: Principal) -> AccessFilter:
    data_roles = [role for role in principal.roles if role in ROLE_CLEARANCE]
    if not data_roles:
        raise Forbidden("no role grants data access")
    if principal.regions is None and all(
        role in ROLES_REQUIRING_REGION_SCOPE for role in data_roles
    ):
        raise Forbidden("region-scoped role without a regions claim")
    clearance = max((ROLE_CLEARANCE[role] for role in data_roles), key=lambda c: c.rank)
    return AccessFilter(
        tenant_id=principal.tenant_id,
        regions=principal.regions,
        brands=principal.brands,
        max_classification=clearance,
    )
