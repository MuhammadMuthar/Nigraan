"""Uniform error envelope: {code, message, field?}. Never a stack trace."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("nigraan")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        self.status, self.code, self.message, self.field = status, code, message, field


def _body(code: str, message: str, field: str | None = None) -> dict:
    out = {"code": code, "message": message}
    if field:
        out["field"] = field
    return out


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message, exc.field), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        err = exc.errors()[0] if exc.errors() else {}
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
        return JSONResponse(_body("validation_error", err.get("msg", "Invalid input"), ".".join(loc) or None),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}.get(exc.status_code, "error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return JSONResponse(_body("internal_error", "Something went wrong on our side. Please retry."), status_code=500)
