"""Error envelope: every error is `{"error": {"code": "SNAKE_CODE", "message": "<vi text>"}}`."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[str] | None = None  # e.g. the validation messages of a refused edit


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """Raised by module services; rendered as the error envelope."""

    def __init__(
        self, status_code: int, code: str, message: str, details: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


_STATUS_CODES: dict[int, tuple[str, str]] = {
    400: ("BAD_REQUEST", "Yêu cầu không hợp lệ."),
    401: ("UNAUTHORIZED", "Cần đăng nhập."),
    403: ("FORBIDDEN", "Không có quyền truy cập."),
    404: ("NOT_FOUND", "Không tìm thấy."),
    405: ("METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ."),
    409: ("CONFLICT", "Xung đột dữ liệu."),
    422: ("VALIDATION_ERROR", "Dữ liệu không hợp lệ."),
    503: ("SERVICE_UNAVAILABLE", "Dịch vụ tạm thời không khả dụng."),
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
    details: list[str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        body.model_dump(exclude_none=True), status_code=status_code, headers=headers
    )


async def _app_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, details=exc.details)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code, message = _STATUS_CODES.get(exc.status_code, ("HTTP_ERROR", "Đã xảy ra lỗi."))
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(422, "VALIDATION_ERROR", "Dữ liệu không hợp lệ.")


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error", exc_info=exc, extra={"path": request.url.path})
    return error_response(500, "INTERNAL_ERROR", "Đã xảy ra lỗi hệ thống.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
