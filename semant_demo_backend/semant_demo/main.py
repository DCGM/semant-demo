from fastapi import FastAPI, Depends, HTTPException, Request
import logging
from time import perf_counter, time
from uuid import uuid4

from semant_demo.config import config
from semant_demo.opentelemetry import setup_logging_export
from semant_demo.rag.rag_factory import rag_factory
from semant_demo.routes.dependencies import cleanup_dependencies, get_engine, get_search, get_summarizer
from fastapi.staticfiles import StaticFiles
import os

from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from semant_demo.schemas import TasksBase
from semant_demo.routes import export_router
from semant_demo.users.auth import auth_router, register_router, users_router
# Import User model so its table is included in TasksBase.metadata
import semant_demo.users.models  # noqa: F401

logging.basicConfig(level=config.LOG_LEVEL)

telemetry = setup_logging_export()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global_engine, _ = get_engine()
    async with global_engine.begin() as conn:
        # create tables
        await conn.run_sync(TasksBase.metadata.create_all)
    #load rags configurations and create instances
    rag_factory(global_config=config, configs_path=config.RAG_CONFIGS_PATH)

    yield

    #shutdown all dependencies
    try:
        await cleanup_dependencies()
        logging.info("Application cleanup complete.")
    finally:
        if telemetry is not None:
            telemetry.shutdown()

#app definition
app = FastAPI(lifespan=lifespan)
# mount routes
app.include_router(export_router)
app.include_router(auth_router, prefix="/api/auth/jwt", tags=["auth"])
app.include_router(register_router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router, prefix="/api/users", tags=["users"])

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    """Create one structured log record for every completed HTTP request."""
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    started_at = perf_counter()
    attributes = {
        "request.id": request_id,
        "http.request.method": request.method,
        "url.path": request.url.path,
    }

    try:
        response = await call_next(request)
    except Exception:
        attributes["http.response.status_code"] = 500
        attributes["http.server.request.duration_ms"] = round(
            (perf_counter() - started_at) * 1000, 2
        )
        logging.getLogger(__name__).exception(
            "HTTP request failed",
            extra=attributes,
        )
        raise

    attributes["http.response.status_code"] = response.status_code
    attributes["http.server.request.duration_ms"] = round(
        (perf_counter() - started_at) * 1000, 2
    )
    logging.getLogger(__name__).info(
        "HTTP request completed",
        extra=attributes,
    )
    response.headers["X-Request-ID"] = request_id
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.ALLOWED_ORIGIN],  # http://localhost:9000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir(config.STATIC_PATH):
    logging.info(f"Serving static files from '{config.STATIC_PATH}' directory")
    app.mount("/", StaticFiles(directory=config.STATIC_PATH,
              html=True), name="static")
else:
    logging.warning(
        f"'{config.STATIC_PATH}' directory not found. Static files will not be served.")
