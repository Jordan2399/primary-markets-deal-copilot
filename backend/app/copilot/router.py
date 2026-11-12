"""Copilot endpoint (server-sent events)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.copilot.models import ChatRequest
from app.copilot.service import CopilotService
from app.core.security import CurrentUser, get_current_user
from app.deps import get_copilot_service

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    service: Annotated[CopilotService, Depends(get_copilot_service)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> StreamingResponse:
    """Ask the Copilot. The response is a stream of server-sent events (see copilot/service.py)."""
    prepared = await service.prepare(request, user)
    return StreamingResponse(
        service.stream(prepared),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
