from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging

from semant_demo.bootstrap import AppResources
from semant_demo.config import Config, config
from semant_demo.features.collections.access import AccessDenied, AuthenticationRequired, ResourceNotFound
from semant_demo.rag.rag_factory import rag_factory
from fastapi.staticfiles import StaticFiles
import os

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from semant_demo.schemas import TasksBase
from semant_demo.routes import export_router
from semant_demo.users.auth import auth_router, register_router, users_router
# Import User model so its table is included in TasksBase.metadata
import semant_demo.users.models  # noqa: F401

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_config: Config = app.state.config
    resources = AppResources.create(app_config)
    app.state.resources = resources
    try:
        async with resources.engine.begin() as conn:
            # create tables
            await conn.run_sync(TasksBase.metadata.create_all)
        #load rags configurations and create instances
        resources.rag = rag_factory(global_config=app_config, configs_path=app_config.RAG_CONFIGS_PATH)

        yield
    finally:
        #shutdown all dependencies, also after a failed startup
        app.state.resources = None
        await resources.close()
        logging.info(f"Application cleanup complete.")


def _detail_handler(status_code: int):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})
    return handler


def create_app(app_config: Config | None = None) -> FastAPI:
    """Build the application. No external service is contacted until startup or first use."""
    app_config = app_config if app_config is not None else Config()

    #app definition
    app = FastAPI(lifespan=lifespan)
    app.state.config = app_config
    app.state.resources = None
    # mount routes
    app.include_router(export_router)
    app.include_router(auth_router, prefix="/api/auth/jwt", tags=["auth"])
    app.include_router(register_router, prefix="/api/auth", tags=["auth"])
    app.include_router(users_router, prefix="/api/users", tags=["users"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Collection access checks (features/collections/access.py) raise these.
    for exc_type, status_code in ((AuthenticationRequired, 401), (ResourceNotFound, 404), (AccessDenied, 403)):
        app.add_exception_handler(exc_type, _detail_handler(status_code))

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

    return app


# Production entry point (`uvicorn semant_demo.main:app`). It shares the process-wide
# `config` with modules that still read it directly (see docs/REFACTOR_STATUS.md).
app = create_app(config)
