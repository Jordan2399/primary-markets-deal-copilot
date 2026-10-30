"""Dependency checks for Neo4j and Ollama. Each check never raises."""

from dataclasses import dataclass, field

import httpx
from neo4j import AsyncGraphDatabase

from app.core.config import Settings


@dataclass
class CheckResult:
    ok: bool
    detail: str
    extra: dict[str, object] = field(default_factory=dict)


async def check_neo4j(settings: Settings) -> CheckResult:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=settings.health_timeout_seconds,
    )
    try:
        await driver.verify_connectivity()
        return CheckResult(ok=True, detail="connected")
    except Exception as exc:  # noqa: BLE001 - report any failure as a status, not a crash
        return CheckResult(ok=False, detail=f"{type(exc).__name__}: {exc}"[:200])
    finally:
        await driver.close()


async def check_ollama(settings: Settings) -> CheckResult:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
        installed = {m.get("name", "") for m in response.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        return CheckResult(ok=False, detail=f"{type(exc).__name__}: {exc}"[:200])

    wanted = [settings.llm_chat_model, settings.llm_embed_model]
    missing = [m for m in wanted if not _has_model(installed, m)]
    if missing:
        return CheckResult(
            ok=False,
            detail="reachable, but models missing: " + ", ".join(missing),
            extra={"missing": missing, "installed": sorted(installed)},
        )
    return CheckResult(ok=True, detail="reachable, models present", extra={"models": wanted})


def _has_model(installed: set[str], wanted: str) -> bool:
    """Ollama lists 'name:tag'; a bare name means ':latest'."""
    if wanted in installed:
        return True
    if ":" not in wanted:
        return f"{wanted}:latest" in installed
    return False
