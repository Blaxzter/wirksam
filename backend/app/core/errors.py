from __future__ import annotations

import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, NoReturn, cast

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.schemas.problem import (
    ProblemDetails,
    ValidationErrorItem,
    coerce_problem_detail,
)

PROBLEM_JSON_MEDIA_TYPE = "application/problem+json"
URN_PREFIX = "urn:problem:"
RESOURCE_NOT_FOUND_RE = re.compile(
    r"^(?P<resource>[A-Za-z][A-Za-z0-9 _-]*)\s+not\s+found$",
    re.IGNORECASE,
)


def _status_title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def _problem_response(
    *,
    status_code: int,
    title: str,
    detail: str | None,
    instance: str | None,
    errors: list[ValidationErrorItem] | None = None,
    code: str | None = None,
    headers: Mapping[str, str] | None = None,
    type_url: str = "about:blank",
) -> JSONResponse:
    payload = ProblemDetails(
        type=type_url,
        code=code,
        title=title,
        status=status_code,
        detail=detail,
        instance=instance,
        errors=errors,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True),
        headers=dict(headers) if headers else None,
        media_type=PROBLEM_JSON_MEDIA_TYPE,
    )


def _normalize_validation_errors(
    exc: RequestValidationError,
) -> list[ValidationErrorItem]:
    items: list[ValidationErrorItem] = []
    for error in exc.errors():
        loc = error.get("loc", [])
        items.append(
            ValidationErrorItem(
                loc=[
                    part if isinstance(part, str | int) else str(part) for part in loc
                ],
                msg=str(error.get("msg", "Invalid value")),
                type=str(error.get("type", "value_error")),
            )
        )
    return items


def _parse_problem_detail(detail: object) -> tuple[str | None, str | None, str | None]:
    if isinstance(detail, dict):
        d = cast(dict[str, Any], detail)
        code = d.get("code")
        code_value = code if isinstance(code, str) else None
        type_url = d.get("type")
        type_value = type_url if isinstance(type_url, str) else None
        if not type_value and code_value:
            type_value = f"urn:problem:{code_value}"
        detail_value: str | None = d.get("detail")
        if not isinstance(detail_value, str):
            detail_value = (
                d.get("message") if isinstance(d.get("message"), str) else None
            )
        return detail_value, type_value, code_value
    return coerce_problem_detail(detail), None, None


def _slugify_resource(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "resource"


def _infer_problem_type(status_code: int, detail: str | None) -> str | None:
    if status_code == 404:
        if detail:
            match = RESOURCE_NOT_FOUND_RE.match(detail)
            if match:
                resource = _slugify_resource(match.group("resource"))
                return f"{URN_PREFIX}{resource}.not_found"
        return f"{URN_PREFIX}not_found"
    if status_code == 401:
        return f"{URN_PREFIX}unauthorized"
    if status_code == 403:
        return f"{URN_PREFIX}forbidden"
    if status_code == 422:
        return f"{URN_PREFIX}validation_error"
    if status_code == 429:
        return f"{URN_PREFIX}rate_limited"
    if status_code == 400:
        return f"{URN_PREFIX}bad_request"
    if status_code >= 500:
        return f"{URN_PREFIX}internal_server_error"
    return None


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    detail, type_url, code = _parse_problem_detail(exc.detail)
    if not detail:
        detail = _status_title(status_code)
    resolved_type_url = (
        type_url or _infer_problem_type(status_code, detail) or "about:blank"
    )
    return _problem_response(
        status_code=status_code,
        title=_status_title(status_code),
        detail=detail,
        instance=str(request.url.path),
        code=code,
        headers=exc.headers,
        type_url=resolved_type_url,
    )


def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status_code = exc.status_code
    detail, type_url, code = _parse_problem_detail(exc.detail)
    if not detail:
        detail = _status_title(status_code)
    resolved_type_url = (
        type_url or _infer_problem_type(status_code, detail) or "about:blank"
    )
    return _problem_response(
        status_code=status_code,
        title=_status_title(status_code),
        detail=detail,
        instance=str(request.url.path),
        code=code,
        headers=exc.headers,
        type_url=resolved_type_url,
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _problem_response(
        status_code=422,
        title="Validation Error",
        detail="Request validation failed.",
        instance=str(request.url.path),
        errors=_normalize_validation_errors(exc),
        type_url=f"{URN_PREFIX}validation_error",
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if settings.ENVIRONMENT == "local":
        detail = f"{type(exc).__name__}: {exc}"
    else:
        detail = "Unexpected error occurred."
    return _problem_response(
        status_code=500,
        title=_status_title(500),
        detail=detail,
        instance=str(request.url.path),
        type_url=f"{URN_PREFIX}internal_server_error",
    )


def problem_detail(
    *, code: str, detail: str | None = None, type_url: str | None = None
) -> dict[str, str]:
    payload = {"code": code, "type": type_url or f"urn:problem:{code}"}
    if detail:
        payload["detail"] = detail
    return payload


def raise_problem(
    status_code: int,
    *,
    code: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=problem_detail(code=code, detail=detail),
        headers=headers,
    )
