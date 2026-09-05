"""Test wiring: isolated SQLite, in-process cache, and fake external clients.

Neither the exchange-rate API nor the budget service is touched by the suite:
both are replaced by doubles, so the tests are deterministic and offline.
"""

import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

_TEMP_DIR = Path(tempfile.mkdtemp(prefix="subscription-api-tests-"))

# Configurado antes de importar a aplicação, que lê as settings no import.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEMP_DIR / 'test.db'}"
os.environ["API_KEY"] = "test-key"
os.environ["REDIS_URL"] = ""
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["IDLE_DAYS_THRESHOLD"] = "30"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.clients.frankfurter_client import FrankfurterError  # noqa: E402
from app.core.cache import InMemoryTTLCache  # noqa: E402
from app.database import SessionFactory, init_database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.subscription import Subscription  # noqa: E402

API_KEY = "test-key"
QUOTE_DATE = date(2026, 9, 4)


class FakeFrankfurterClient:
    """Stand-in for the external exchange-rate API."""

    def __init__(self) -> None:
        self.rates = {"USD": Decimal("5.00"), "EUR": Decimal("6.00")}
        self.available = True
        self.rate_calls = 0

    async def fetch_rate(self, currency: str, target: str = "BRL") -> tuple[Decimal, date]:
        self.rate_calls += 1
        if not self.available:
            raise FrankfurterError("API de câmbio indisponível (simulado)")
        if currency.upper() not in self.rates:
            raise FrankfurterError(f"moeda {currency} não cotada")
        return self.rates[currency.upper()], QUOTE_DATE

    async def fetch_currencies(self) -> dict[str, str]:
        if not self.available:
            raise FrankfurterError("API de câmbio indisponível (simulado)")
        return {"BRL": "Brazilian Real", "USD": "US Dollar", "EUR": "Euro"}


class FakeBudgetClient:
    """Stand-in for the secondary component."""

    def __init__(self) -> None:
        self.available = True
        self.last_evaluation_payload: dict[str, Any] | None = None
        self.last_projection_payload: dict[str, Any] | None = None

    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.last_evaluation_payload = payload
        if not self.available:
            return None
        return {"overall_status": "OK", "results": [], "unbudgeted_categories": []}

    async def project(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.last_projection_payload = payload
        if not self.available:
            return None
        return {"total_brl": 1234.0, "months": payload["months"], "timeline": []}

    async def ping(self) -> bool:
        return self.available


@pytest.fixture(autouse=True)
async def clean_database():
    """Every test starts from an empty subscriptions table."""
    await init_database()
    async with SessionFactory() as session:
        await session.execute(delete(Subscription))
        await session.commit()
    yield


@pytest.fixture
def exchange_api() -> FakeFrankfurterClient:
    return FakeFrankfurterClient()


@pytest.fixture
def budget_api() -> FakeBudgetClient:
    return FakeBudgetClient()


@pytest.fixture
def app_instance(exchange_api, budget_api):
    app = create_app()
    # O lifespan não roda sob ASGITransport, então o estado é montado aqui.
    app.state.cache = InMemoryTTLCache()
    app.state.frankfurter_client = exchange_api
    app.state.budget_client = budget_api
    return app


@pytest.fixture
async def client(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"X-API-Key": API_KEY},
    ) as http_client:
        yield http_client


@pytest.fixture
async def anonymous_client(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def subscription_payload(**overrides: Any) -> dict[str, Any]:
    """Valid creation payload, overridable field by field."""
    payload = {
        "name": "Streaming Plus",
        "vendor": "Acme Streaming",
        "category": "STREAMING",
        "amount": 10.00,
        "currency": "USD",
        "billing_cycle": "MONTHLY",
        "started_on": "2026-01-10",
        "next_renewal_on": "2026-10-10",
        "status": "ACTIVE",
        "last_used_on": "2026-09-01",
    }
    payload.update(overrides)
    return payload


async def create_subscription(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/subscriptions", json=subscription_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()
