from collections.abc import Iterator
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from ccvie.adapters.cache.memory import MemoryCache
from ccvie.api.app import create_app
from ccvie.bootstrap.container import Container
from ccvie.config import Settings
from ccvie.core.models import Role
from ccvie.data_foundation.db import Database
from ccvie.data_foundation.migrate import migration_files
from ccvie.security.authn import TokenVerifier
from ccvie.security.dev_tokens import mint_dev_token


class FakeDatabase:
    def __init__(self, settings: Settings, *, healthy: bool = True) -> None:
        self._healthy = healthy
        self._migrations = {path.stem for path in migration_files(settings.migrations_dir)}
        self._dimension = settings.embedding_dimension

    async def ping(self) -> bool:
        if not self._healthy:
            raise ConnectionRefusedError
        return True

    async def applied_migrations(self) -> set[str]:
        return self._migrations if self._healthy else set()

    async def embedding_dimension(self) -> int | None:
        return self._dimension if self._healthy else None

    async def close(self) -> None:
        return None


def client_for(settings: Settings, *, healthy: bool = True) -> TestClient:
    async def factory(app_settings: Settings) -> Container:
        return Container(
            settings=app_settings,
            db=cast(Database, FakeDatabase(app_settings, healthy=healthy)),
            cache=MemoryCache(),
            verifier=TokenVerifier(app_settings),
        )

    return TestClient(create_app(settings, factory))


@pytest.fixture
def client(dev_settings: Settings) -> Iterator[TestClient]:
    with client_for(dev_settings) as test_client:
        yield test_client


def bearer(settings: Settings, tenant: UUID, *roles: Role) -> dict[str, str]:
    token = mint_dev_token(settings, user_id="u1", tenant_id=tenant, roles=roles, regions=["south"])
    return {"Authorization": f"Bearer {token}"}


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": None}
    UUID(response.headers["X-Request-ID"])


def test_request_id_is_echoed_when_valid(client: TestClient) -> None:
    request_id = str(uuid4())
    assert (
        client.get("/healthz", headers={"X-Request-ID": request_id}).headers["X-Request-ID"]
        == request_id
    )
    assert (
        client.get("/healthz", headers={"X-Request-ID": "not-a-uuid"}).headers["X-Request-ID"]
        != "not-a-uuid"
    )


def test_readyz_ok(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert set(body["checks"]) == {"database", "migrations", "embedding_dimension", "cache"}


def test_readyz_503_when_database_down(dev_settings: Settings) -> None:
    with client_for(dev_settings, healthy=False) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    checks = response.json()["checks"]
    assert checks["database"] == {"ok": False, "detail": "ConnectionRefusedError"}
    assert checks["cache"]["ok"] is True


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == "unauthenticated"


def test_me_rejects_garbage_token(client: TestClient) -> None:
    response = client.get("/v1/me", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_me_returns_verified_principal(client: TestClient, dev_settings: Settings) -> None:
    tenant = uuid4()
    response = client.get("/v1/me", headers=bearer(dev_settings, tenant, Role.QUALITY_MANAGER))
    assert response.status_code == 200
    body = response.json()
    assert body["tenantId"] == str(tenant)
    assert body["roles"] == ["quality_manager"]
    assert "actions:confirm" in body["capabilities"]
    assert body["regions"] == ["south"]


def test_metrics_exposed(client: TestClient) -> None:
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ccvie_http_request_duration_seconds" in response.text
