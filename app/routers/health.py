"""Liveness endpoint reporting the real state of each dependency."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.budget_client import BudgetClient
from app.clients.frankfurter_client import FrankfurterClient, FrankfurterError
from app.config import Settings, get_settings
from app.database import get_session
from app.dependencies import get_budget_client, get_frankfurter_client
from app.schemas.common import DependencyHealth, HealthResponse

router = APIRouter(tags=["Operação"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verifica a saúde do serviço e de suas dependências",
    description="Rota aberta, sem autenticação, para uso do Docker e de quem estiver operando o serviço.",
)
async def health(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    budget_client: BudgetClient = Depends(get_budget_client),
    frankfurter_client: FrankfurterClient = Depends(get_frankfurter_client),
) -> HealthResponse:
    dependencies = [
        await _check_database(session),
        _check_cache(request),
        await _check_budget_service(budget_client),
        await _check_exchange_api(frankfurter_client, settings.base_currency),
    ]
    degraded = any(dependency.status != "up" for dependency in dependencies)

    return HealthResponse(
        status="degraded" if degraded else "healthy",
        service=settings.app_name,
        version=settings.app_version,
        dependencies=dependencies,
    )


async def _check_database(session: AsyncSession) -> DependencyHealth:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health nunca deve levantar
        return DependencyHealth(name="database", status="down", detail=str(exc))
    return DependencyHealth(name="database", status="up", detail="sqlite")


def _check_cache(request: Request) -> DependencyHealth:
    cache = request.app.state.cache
    if cache.backend == "redis":
        return DependencyHealth(name="cache", status="up", detail="redis")
    return DependencyHealth(
        name="cache",
        status="degraded",
        detail="cache em memória (Redis indisponível ou não configurado)",
    )


async def _check_budget_service(client: BudgetClient) -> DependencyHealth:
    if await client.ping():
        return DependencyHealth(name="budget-api", status="up", detail="componente secundária")
    return DependencyHealth(
        name="budget-api",
        status="down",
        detail="indisponível; a visão consolidada será devolvida sem avaliação de metas",
    )


async def _check_exchange_api(client: FrankfurterClient, base_currency: str) -> DependencyHealth:
    try:
        await client.fetch_rate("USD", base_currency)
    except FrankfurterError as exc:
        return DependencyHealth(
            name="frankfurter",
            status="down",
            detail=f"API externa de câmbio indisponível: {exc}",
        )
    return DependencyHealth(name="frankfurter", status="up", detail="API externa de câmbio")
