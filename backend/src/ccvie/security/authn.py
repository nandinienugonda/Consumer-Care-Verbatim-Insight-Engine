"""Bearer-token verification. Identity comes only from a verified token."""

import logging
from collections.abc import Mapping
from uuid import UUID

import jwt

from ccvie.config import Settings
from ccvie.core.errors import Unauthenticated
from ccvie.core.models import Principal, Role

logger = logging.getLogger(__name__)

DEV_ALGORITHMS = ["HS256"]
JWKS_ALGORITHMS = ["RS256", "ES256"]
REQUIRED_CLAIMS = ["exp", "iat", "iss", "aud", "sub", "tid"]
MIN_DEV_SECRET_LENGTH = 32


class TokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self._issuer = settings.auth_issuer
        self._audience = settings.auth_audience
        self._dev_secret: str | None = None
        self._jwks: jwt.PyJWKClient | None = None
        if settings.auth_dev_mode:
            secret = settings.auth_dev_secret.get_secret_value()
            if len(secret) < MIN_DEV_SECRET_LENGTH:
                raise ValueError(
                    f"AUTH_DEV_SECRET must be at least {MIN_DEV_SECRET_LENGTH} characters"
                )
            self._dev_secret = secret
        elif settings.auth_jwks_url:
            self._jwks = jwt.PyJWKClient(settings.auth_jwks_url, cache_keys=True)
        else:
            raise ValueError("set AUTH_JWKS_URL, or AUTH_DEV_MODE=true for local development")

    def verify(self, token: str) -> Principal:
        try:
            if self._dev_secret is not None:
                key: object = self._dev_secret
                algorithms = DEV_ALGORITHMS
            else:
                assert self._jwks is not None
                key = self._jwks.get_signing_key_from_jwt(token).key
                algorithms = JWKS_ALGORITHMS
            claims = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            raise Unauthenticated("invalid or expired token") from exc
        return principal_from_claims(claims)


def principal_from_claims(claims: Mapping[str, object]) -> Principal:
    try:
        tenant_id = UUID(str(claims["tid"]))
    except ValueError as exc:
        raise Unauthenticated("tid claim is not a UUID") from exc

    roles: set[Role] = set()
    for raw in _string_list(claims.get("roles")) or ():
        try:
            roles.add(Role(raw))
        except ValueError:
            logger.warning("ignoring unknown role claim", extra={"role": raw})

    return Principal(
        user_id=str(claims["sub"]),
        tenant_id=tenant_id,
        roles=frozenset(roles),
        scopes=frozenset(_string_list(claims.get("scp")) or ()),
        regions=_optional_set(claims.get("regions")),
        brands=_optional_set(claims.get("brands")),
    )


def _string_list(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise Unauthenticated("malformed list claim")


def _optional_set(value: object) -> frozenset[str] | None:
    items = _string_list(value)
    return None if items is None else frozenset(items)
