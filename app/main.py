"""Application entry point for the subscription service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.clients.budget_client import BudgetClient
from app.clients.frankfurter_client import FrankfurterClient
from app.config import get_settings
from app.core.cache import build_cache
from app.core.correlation import CorrelationIdMiddleware
from app.core.docs import register_documentation_routes
from app.core.errors import register_exception_handlers
from app.database import engine, init_database
from app.routers import fx, health, insights, subscriptions

DESCRIPTION = """
Componente **principal** do MVP de controle de assinaturas digitais.

Registra as assinaturas na moeda original, consome a **API externa de câmbio
[Frankfurter](https://frankfurter.dev)** para normalizar todos os custos em reais e orquestra a
componente secundária (`mvp-budget-api`) para avaliar o gasto contra as metas e projetar o
desembolso dos próximos meses.

A cotação obtida da API externa é tratada e **gravada junto da assinatura**, preservando quanto
ela custava no momento da contratação — os dados externos são consumidos e transformados, nunca
apenas repassados.

Todas as rotas de negócio exigem o cabeçalho `X-API-Key`. A rota `/health` é aberta.
"""


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    await init_database()
    app.state.cache = await build_cache(settings.redis_url)
    app.state.frankfurter_client = FrankfurterClient(
        settings.frankfurter_url, settings.frankfurter_timeout_seconds
    )
    app.state.budget_client = BudgetClient(
        settings.budget_api_url,
        settings.budget_api_key,
        settings.budget_api_timeout_seconds,
        settings.budget_api_retries,
    )
    logger.info("cache ativo: %s", app.state.cache.backend)
    logger.info("serviço de metas em %s", settings.budget_api_url)

    if settings.seed_on_startup:
        from seeds.seed import seed_subscriptions

        created = await seed_subscriptions()
        logger.info("seed concluído, %s assinaturas garantidas", created)

    yield

    await app.state.cache.close()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="MVP Subscription API",
        description=DESCRIPTION,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        contact={"name": "MVP - Arquitetura de Software (PUC-Rio)"},
        license_info={"name": "MIT"},
    )

    register_documentation_routes(app)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(subscriptions.router)
    app.include_router(insights.router)
    app.include_router(fx.router)

    return app


app = create_app()
