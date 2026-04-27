from fastapi import FastAPI, Depends, HTTPException
import logging

from semant_demo.config import config
from semant_demo.rag.rag_factory import rag_factory
from semant_demo.routes.dependencies import cleanup_dependencies, get_engine, get_search, get_summarizer
from time import time
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
    global_engine, _ = get_engine()
    async with global_engine.begin() as conn:
        # create tables
        await conn.run_sync(TasksBase.metadata.create_all)
    #load rags configurations and create instances
    rag_factory(global_config=config, configs_path=config.RAG_CONFIGS_PATH)

    yield

    #shutdown all dependencies
    await cleanup_dependencies()
    logging.info(f"Application cleanup complete.")

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