"""Health endpoints.

/health/live  : the API process is up (used by the container health check).
/health       : the API plus its dependencies (Neo4j, Ollama).
"""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.health import service

router = APIRouter(prefix="/health", tags=["health"])


class DependencyStatus(BaseModel):
    ok: bool
    detail: str
    extra: dict[str, object] = {}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    llm_provider: str
    dependencies: dict[str, DependencyStatus]


class LiveResponse(BaseModel):
    status: Literal["ok"]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    neo4j_result, ollama_result = await asyncio.gather(
        service.check_neo4j(settings), service.check_ollama(settings)
    )
    deps = {
        "neo4j": DependencyStatus(**neo4j_result.__dict__),
        "ollama": DependencyStatus(**ollama_result.__dict__),
    }
    overall: Literal["ok", "degraded"] = "ok" if all(d.ok for d in deps.values()) else "degraded"
    return HealthResponse(
        status=overall,
        version=settings.app_version,
        environment=settings.app_env,
        llm_provider=settings.llm_provider,
        dependencies=deps,
    )
