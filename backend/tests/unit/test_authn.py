from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import SecretStr

from ccvie.config import Settings
from ccvie.core.errors import Unauthenticated
from ccvie.core.models import Role
from ccvie.security.authn import TokenVerifier
from ccvie.security.dev_tokens import mint_dev_token
from tests.conftest import DEV_SECRET


def claims(settings: Settings, **overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    base: dict[str, object] = {
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "sub": "u1",
        "tid": str(uuid4()),
        "roles": ["care_analyst"],
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    base.update(overrides)
    return base


def test_valid_dev_token_yields_principal(dev_settings: Settings) -> None:
    tenant = uuid4()
    token = mint_dev_token(
        dev_settings,
        user_id="analyst-1",
        tenant_id=tenant,
        roles=[Role.CARE_ANALYST],
        regions=["south"],
        scopes=["tools:care_ops:read"],
    )
    principal = TokenVerifier(dev_settings).verify(token)
    assert principal.user_id == "analyst-1"
    assert principal.tenant_id == tenant
    assert principal.roles == {Role.CARE_ANALYST}
    assert principal.regions == {"south"}
    assert principal.brands is None
    assert principal.scopes == {"tools:care_ops:read"}


@pytest.mark.parametrize(
    "bad",
    [
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"aud": "someone-else"},
        {"iss": "someone-else"},
        {"tid": "not-a-uuid"},
    ],
)
def test_rejects_invalid_claims(dev_settings: Settings, bad: dict[str, object]) -> None:
    token = jwt.encode(claims(dev_settings, **bad), DEV_SECRET, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        TokenVerifier(dev_settings).verify(token)


def test_rejects_missing_tenant(dev_settings: Settings) -> None:
    payload = claims(dev_settings)
    del payload["tid"]
    token = jwt.encode(payload, DEV_SECRET, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        TokenVerifier(dev_settings).verify(token)


def test_rejects_wrong_signature(dev_settings: Settings) -> None:
    token = jwt.encode(claims(dev_settings), "x" * 40, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        TokenVerifier(dev_settings).verify(token)


def test_rejects_unsigned_token(dev_settings: Settings) -> None:
    token = jwt.encode(claims(dev_settings), key=None, algorithm="none")
    with pytest.raises(Unauthenticated):
        TokenVerifier(dev_settings).verify(token)


def test_unknown_roles_are_dropped(dev_settings: Settings) -> None:
    token = jwt.encode(
        claims(dev_settings, roles=["care_analyst", "superuser"]), DEV_SECRET, algorithm="HS256"
    )
    assert TokenVerifier(dev_settings).verify(token).roles == {Role.CARE_ANALYST}


def test_short_dev_secret_is_refused() -> None:
    settings = Settings(_env_file=None, auth_dev_mode=True, auth_dev_secret=SecretStr("short"))
    with pytest.raises(ValueError, match="AUTH_DEV_SECRET"):
        TokenVerifier(settings)


def test_production_mode_requires_jwks() -> None:
    with pytest.raises(ValueError, match="AUTH_JWKS_URL"):
        TokenVerifier(Settings(_env_file=None, auth_dev_mode=False, auth_jwks_url=None))


def test_dev_tokens_refused_outside_dev_mode() -> None:
    with pytest.raises(RuntimeError):
        mint_dev_token(
            Settings(_env_file=None, auth_dev_mode=False),
            user_id="u",
            tenant_id=uuid4(),
            roles=[Role.CARE_ANALYST],
        )
