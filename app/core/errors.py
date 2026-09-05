"""Uniform error payloads, shaped after RFC 7807 (Problem Details)."""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.correlation import get_request_id

logger = logging.getLogger(__name__)


class ProblemDetail(BaseModel):
    """Error body returned by every failing route."""

    type: str = Field(description="Identificador estável do tipo de erro.")
    title: str = Field(description="Resumo legível do erro.")
    status: int = Field(description="Código HTTP correspondente.")
    detail: str = Field(description="Explicação específica desta ocorrência.")
    request_id: str | None = Field(default=None, description="Correlação da requisição.")
    errors: list[dict] | None = Field(default=None, description="Falhas de validação, campo a campo.")


class DomainError(Exception):
    """Business rule violation that maps onto an HTTP status."""

    def __init__(self, detail: str, *, status_code: int = status.HTTP_400_BAD_REQUEST, error_type: str = "domain-error"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.error_type = error_type


def _problem(status_code: int, title: str, detail: str, error_type: str, errors: list[dict] | None = None) -> JSONResponse:
    body = ProblemDetail(
        type=error_type,
        title=title,
        status=status_code,
        detail=detail,
        request_id=get_request_id(),
        errors=errors,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the handlers that turn exceptions into ProblemDetail responses."""

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _problem(exc.status_code, "Regra de negócio violada", exc.detail, exc.error_type)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return _problem(exc.status_code, "Requisição não pôde ser atendida", str(exc.detail), "http-error")

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(part) for part in err["loc"][1:]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Dados da requisição inválidos",
            "Um ou mais campos não passaram na validação.",
            "validation-error",
            errors,
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("erro não tratado", exc_info=exc)
        return _problem(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Erro interno",
            "Ocorreu um erro inesperado ao processar a requisição.",
            "internal-error",
        )
