from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

from semant_demo.bootstrap import AppResources, WeaviateConnector
from semant_demo.adapters.weaviate.client import connect_weaviate
from semant_demo.config import Config, config
from semant_demo.core.errors import IncompleteWriteError, InvalidRequestError, NotFoundError
from semant_demo.features.collections.access import AccessDenied, AuthenticationRequired
from semant_demo.opentelemetry import RequestTelemetryMiddleware, initialize_opentelemetry
from semant_demo.rag.rag_factory import rag_factory
from fastapi.staticfiles import StaticFiles
import os

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from semant_demo.adapters.sql.tables import create_tables
from semant_demo.routes import export_router
from semant_demo.users.auth import auth_router, register_router, users_router

logging.basicConfig(level=config.LOG_LEVEL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_config: Config = app.state.config
    resources = AppResources.create(app_config)
    app.state.resources = resources
    try:
        await create_tables(resources.engine)
        # One Weaviate client for the application's lifetime; startup fails without it.
        await resources.connect_weaviate(app.state.weaviate_connector)
        #load rags configurations and create instances
        resources.rag = rag_factory(global_config=app_config, configs_path=app_config.RAG_CONFIGS_PATH)

        yield
    finally:
        #shutdown all dependencies, also after a failed startup
        app.state.resources = None
        try:
            await resources.close()
            logging.info("Application cleanup complete.")
        finally:
            if app.state.telemetry is not None:
                app.state.telemetry.shutdown()


def _detail_handler(status_code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})
    return handler


def create_app(app_config: Config | None = None, *, weaviate_connector: WeaviateConnector | None = None) -> FastAPI:
    """Build the application. No external service is contacted before startup.

    ``weaviate_connector`` opens the Weaviate client at startup (default: the configured
    instance); tests that do not use Weaviate pass a stand-in.
    """
    app_config = app_config if app_config is not None else Config()
    # Disabled by default (OTEL_ENABLED), so tests and local runs export nothing.
    telemetry = initialize_opentelemetry(app_config)

    #app definition
    app = FastAPI(lifespan=lifespan)
    app.state.config = app_config
    app.state.resources = None
    app.state.telemetry = telemetry
    app.state.weaviate_connector = weaviate_connector or connect_weaviate
    # mount routes
    app.include_router(export_router)
    app.include_router(auth_router, prefix="/api/auth/jwt", tags=["auth"])
    app.include_router(register_router, prefix="/api/auth", tags=["auth"])
    app.include_router(users_router, prefix="/api/users", tags=["users"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Raised by collection access checks (features/collections/access.py, its
    # ResourceNotFound is a NotFoundError) and by repositories/services (core/errors.py).
    for exc_type, status_code in ((AuthenticationRequired, 401), (NotFoundError, 404), (AccessDenied, 403),
                                  (InvalidRequestError, 400)):
        app.add_exception_handler(exc_type, _detail_handler(status_code))

    # A multi-step write that stopped part way: completed steps are kept (ADR 0002).
    async def incomplete_write(request: Request, exc: IncompleteWriteError) -> JSONResponse:
        return JSONResponse(status_code=500, content=exc.body())
    app.add_exception_handler(IncompleteWriteError, incomplete_write)

    app.add_middleware(RequestTelemetryMiddleware, telemetry=telemetry)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_config.ALLOWED_ORIGIN],  # http://localhost:9000
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if os.path.isdir(app_config.STATIC_PATH):
        logging.info(f"Serving static files from '{app_config.STATIC_PATH}' directory")
        app.mount("/", StaticFiles(directory=app_config.STATIC_PATH,
                  html=True), name="static")
    else:
        logging.warning(
            f"'{app_config.STATIC_PATH}' directory not found. Static files will not be served.")

    if telemetry is not None:
        telemetry.instrument_app(app)

    return app


# Production entry point (`uvicorn semant_demo.main:app`). It shares the process-wide
# `config` with modules that still read it directly (see docs/REFACTOR_STATUS.md).
app = create_app(config)
