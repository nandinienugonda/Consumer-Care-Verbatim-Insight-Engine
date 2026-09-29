from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ccvie import __version__
from ccvie.api.middleware import handle_ccvie_error, request_context
from ccvie.api.routes import health, me
from ccvie.bootstrap.container import Container, build_container
from ccvie.config import Settings, settings
from ccvie.core.errors import CCVIEError
from ccvie.observability.logging import configure_logging
from ccvie.observability.tracing import configure_tracing

ContainerFactory = Callable[[Settings], Awaitable[Container]]


def create_app(
    app_settings: Settings = settings, container_factory: ContainerFactory = build_container
) -> FastAPI:
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await container_factory(app_settings)
        app.state.container = container
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(title="CCVIE", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(request_context)
    app.add_exception_handler(CCVIEError, handle_ccvie_error)
    app.include_router(health.router)
    app.include_router(me.router, prefix="/v1")
    configure_tracing(app, app_settings)
    return app


app = create_app()
