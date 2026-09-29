from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ccvie.bootstrap.container import Container
from ccvie.core.errors import Unauthenticated
from ccvie.core.models import Principal
from ccvie.security.policy import Capability, authorize

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


# Sync on purpose: FastAPI runs it in a worker thread, so a JWKS fetch cannot block the loop.
def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    container: Annotated[Container, Depends(get_container)],
) -> Principal:
    if credentials is None:
        raise Unauthenticated("missing bearer token")
    return container.verifier.verify(credentials.credentials)


def require(capability: Capability) -> Callable[[Principal], Principal]:
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        authorize(principal, capability)
        return principal

    return dependency
