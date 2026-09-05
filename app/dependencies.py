"""Dependency wiring: routers ask for services, never for clients or sessions."""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.budget_client import BudgetClient
from app.clients.frankfurter_client import FrankfurterClient
from app.config import Settings, get_settings
from app.core.cache import Cache
from app.database import get_session
from app.repositories.subscription_repository import SubscriptionRepository
from app.services.fx_service import FxService
from app.services.insight_service import InsightService
from app.services.subscription_service import SubscriptionService


def get_cache(request: Request) -> Cache:
    """The cache backend chosen at startup, shared by the whole application."""
    return request.app.state.cache


def get_budget_client(request: Request) -> BudgetClient:
    return request.app.state.budget_client


def get_frankfurter_client(request: Request) -> FrankfurterClient:
    return request.app.state.frankfurter_client


def get_subscription_repository(
    session: AsyncSession = Depends(get_session),
) -> SubscriptionRepository:
    return SubscriptionRepository(session)


def get_fx_service(
    client: FrankfurterClient = Depends(get_frankfurter_client),
    cache: Cache = Depends(get_cache),
    settings: Settings = Depends(get_settings),
) -> FxService:
    return FxService(
        client,
        cache,
        settings.base_currency,
        settings.fx_cache_ttl_seconds,
        settings.fx_fallback_ttl_seconds,
    )


def get_subscription_service(
    repository: SubscriptionRepository = Depends(get_subscription_repository),
    fx_service: FxService = Depends(get_fx_service),
) -> SubscriptionService:
    return SubscriptionService(repository, fx_service)


def get_insight_service(
    repository: SubscriptionRepository = Depends(get_subscription_repository),
    budget_client: BudgetClient = Depends(get_budget_client),
    settings: Settings = Depends(get_settings),
) -> InsightService:
    return InsightService(repository, budget_client, settings.idle_days_threshold)
