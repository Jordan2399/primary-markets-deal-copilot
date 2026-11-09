"""Application errors and their JSON representation.

Every error the API returns has the same shape, so the frontend needs one parser:

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": {...}}}
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()


class AppError(Exception):
    """Base class for errors that are safe to show to the caller."""

    status_code = 500
    code = "internal_error"
    retry = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class UpstreamError(AppError):
    """A dependency (usually the LLM) failed. The caller may retry."""

    status_code = 502
    code = "upstream_error"
    retry = True


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "-"))


def _response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retry: bool = False,
) -> JSONResponse:
    body: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": _request_id(request),
        "details": details or {},
    }
    if retry:
        body["retry"] = True
    return JSONResponse(status_code=status_code, content={"error": body})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _response(request, exc.status_code, exc.code, exc.message, exc.details, exc.retry)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _response(
            request,
            422,
            "validation_error",
            "The request is not valid.",
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _response(request, exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Neo4jError)
    @app.exception_handler(DriverError)
    async def handle_database(request: Request, exc: Exception) -> JSONResponse:
        log.error("database_error", error=type(exc).__name__, detail=str(exc)[:300])
        return _response(
            request,
            503,
            "database_unavailable",
            "The database is not available. Check the Neo4j container and credentials.",
            retry=True,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error=type(exc).__name__, detail=str(exc)[:300])
        return _response(request, 500, "internal_error", "Something went wrong on our side.")
