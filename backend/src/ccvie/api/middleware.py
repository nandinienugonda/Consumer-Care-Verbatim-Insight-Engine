import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from ccvie.contracts.errors import ErrorResponse
from ccvie.core.errors import CCVIEError
from ccvie.observability.logging import request_id_var
from ccvie.observability.metrics import REQUEST_LATENCY, REQUESTS_REJECTED

logger = logging.getLogger(__name__)


def _valid_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = _valid_request_id(request.headers.get("x-request-id")) or str(uuid4())
    token = request_id_var.set(request_id)
    start = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = getattr(request.scope.get("route"), "path", "unmatched")
        REQUEST_LATENCY.labels(request.method, route, str(status)).observe(perf_counter() - start)
        request_id_var.reset(token)


async def handle_ccvie_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CCVIEError)
    if exc.status_code in (401, 403):
        REQUESTS_REJECTED.labels(exc.code).inc()
    if exc.status_code >= 500:
        logger.error("request failed", extra={"code": exc.code}, exc_info=exc)
    body = ErrorResponse(
        code=exc.code,
        message=exc.message if exc.status_code < 500 else "internal error",
        requestId=request_id_var.get(),
    )
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(), headers=headers)
