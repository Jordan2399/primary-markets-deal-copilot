"""FastAPI entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit.router import router as audit_router
from app.copilot.router import router as copilot_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.db.neo4j import Neo4jClient
from app.db.schema import ensure_schema
from app.deals.router import router as deals_router
from app.health.router import router as health_router
from app.llm.factory import create_provider

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    db = Neo4jClient(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database
    )
    llm = create_provider(settings)
    app.state.neo4j = db
    app.state.llm = llm
    try:
        await ensure_schema(db, settings.embed_dimensions)
    except Exception as exc:  # noqa: BLE001 - the API must still start; /health reports the problem
        log.warning("schema_setup_failed", error=type(exc).__name__, detail=str(exc)[:200])
    try:
        yield
    finally:
        await llm.aclose()
        await db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Primary Markets Deal Copilot API",
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(deals_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(copilot_router, prefix="/api/v1")
    return app


app = create_app()
