"""Local development token issuer. Refuses to run unless AUTH_DEV_MODE is on."""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from ccvie.config import Settings
from ccvie.core.models import Role


def mint_dev_token(
    settings: Settings,
    *,
    user_id: str,
    tenant_id: UUID,
    roles: Iterable[Role],
    regions: Iterable[str] | None = None,
    brands: Iterable[str] | None = None,
    scopes: Iterable[str] = (),
    ttl: timedelta = timedelta(hours=1),
) -> str:
    if not settings.auth_dev_mode:
        raise RuntimeError("dev tokens are only available with AUTH_DEV_MODE=true")
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "sub": user_id,
        "tid": str(tenant_id),
        "roles": [role.value for role in roles],
        "scp": " ".join(scopes),
        "iat": now,
        "exp": now + ttl,
    }
    if regions is not None:
        claims["regions"] = list(regions)
    if brands is not None:
        claims["brands"] = list(brands)
    return jwt.encode(claims, settings.auth_dev_secret.get_secret_value(), algorithm="HS256")
