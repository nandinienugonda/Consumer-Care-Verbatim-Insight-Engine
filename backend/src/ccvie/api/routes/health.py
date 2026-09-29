import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ccvie.api.deps import get_container
from ccvie.bootstrap.container import Container
from ccvie.contracts.health import CheckResult, ReadinessReport
from ccvie.data_foundation.migrate import migration_files

CHECK_TIMEOUT_S = 2.0

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> CheckResult:
    return CheckResult(ok=True)


async def _run(check: Callable[[], Awaitable[CheckResult]]) -> CheckResult:
    try:
        return await asyncio.wait_for(check(), CHECK_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - any failure means "not ready"
        return CheckResult(ok=False, detail=type(exc).__name__)


@router.get("/readyz", responses={503: {"model": ReadinessReport}})
async def readyz(
    container: Annotated[Container, Depends(get_container)], response: Response
) -> ReadinessReport:
    settings = container.settings

    async def database() -> CheckResult:
        return CheckResult(ok=await container.db.ping())

    async def migrations() -> CheckResult:
        expected = {path.stem for path in migration_files(settings.migrations_dir)}
        missing = sorted(expected - await container.db.applied_migrations())
        return CheckResult(
            ok=not missing, detail=f"missing: {', '.join(missing)}" if missing else None
        )

    async def embedding_dimension() -> CheckResult:
        actual = await container.db.embedding_dimension()
        ok = actual == settings.embedding_dimension
        return CheckResult(
            ok=ok, detail=None if ok else f"db={actual} config={settings.embedding_dimension}"
        )

    async def cache() -> CheckResult:
        return CheckResult(ok=await container.cache.ping())

    names = ("database", "migrations", "embedding_dimension", "cache")
    results = await asyncio.gather(
        *(_run(check) for check in (database, migrations, embedding_dimension, cache))
    )
    report = ReadinessReport(
        ready=all(result.ok for result in results), checks=dict(zip(names, results, strict=True))
    )
    if not report.ready:
        response.status_code = 503
    return report


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
