"""Доменные исключения и их перевод в RFC 9457 `application/problem+json`."""

from http import HTTPStatus

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://sborshik.local/problems/"

logger = structlog.get_logger(__name__)


class DomainError(Exception):
    """Базовое доменное исключение. Сервисы бросают его наследников."""

    status: int = HTTPStatus.BAD_REQUEST
    code: str = "domain-error"
    title: str = "Ошибка запроса"

    def __init__(self, detail: str | None = None, **extra: object) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.extra = extra


class NotFoundError(DomainError):
    """Запрошенный объект не найден."""

    status = HTTPStatus.NOT_FOUND
    code = "not-found"
    title = "Объект не найден"


class ConflictError(DomainError):
    """Состояние объекта не позволяет выполнить операцию."""

    status = HTTPStatus.CONFLICT
    code = "conflict"
    title = "Конфликт состояния"


class PermissionDeniedError(DomainError):
    """Недостаточно прав для операции."""

    status = HTTPStatus.FORBIDDEN
    code = "forbidden"
    title = "Недостаточно прав"


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str | None,
    instance: str,
    **extra: object,
) -> JSONResponse:
    """Собирает ответ в формате problem+json."""
    body: dict[str, object] = {
        "type": PROBLEM_TYPE_BASE + code,
        "title": title,
        "status": status,
        "instance": instance,
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_CONTENT_TYPE)


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101  # гарантируется регистрацией обработчика
    return problem_response(
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        instance=request.url.path,
        **exc.extra,
    )


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    status = exc.status_code
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "Ошибка"
    return problem_response(
        status=status,
        code=f"http-{status}",
        title=title,
        detail=str(exc.detail) if exc.detail else None,
        instance=request.url.path,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    return problem_response(
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="validation-error",
        title="Некорректные данные запроса",
        detail="Проверьте поля запроса",
        instance=request.url.path,
        errors=errors,
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return problem_response(
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="internal-error",
        title="Внутренняя ошибка сервера",
        detail=None,
        instance=request.url.path,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Подключает обработчики, переводящие исключения в problem+json."""
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
