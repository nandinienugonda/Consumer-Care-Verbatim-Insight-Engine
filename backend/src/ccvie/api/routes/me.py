from typing import Annotated

from fastapi import APIRouter, Depends

from ccvie.api.deps import get_principal
from ccvie.contracts.auth import PrincipalView
from ccvie.contracts.errors import ErrorResponse
from ccvie.core.models import Principal
from ccvie.security.policy import capabilities

router = APIRouter(tags=["auth"], responses={401: {"model": ErrorResponse}})


@router.get("/me")
def me(principal: Annotated[Principal, Depends(get_principal)]) -> PrincipalView:
    return PrincipalView(
        userId=principal.user_id,
        tenantId=principal.tenant_id,
        roles=sorted(role.value for role in principal.roles),
        capabilities=sorted(capability.value for capability in capabilities(principal)),
        regions=sorted(principal.regions) if principal.regions is not None else None,
        brands=sorted(principal.brands) if principal.brands is not None else None,
    )
