"""Idempotent synthetic data, so a fresh container is demo-ready.

The rates are fetched from the external API when it is reachable; otherwise a
conservative placeholder keeps the seed working offline.
"""

import asyncio
from datetime import date, timedelta
from decimal import Decimal

from app.clients.frankfurter_client import FrankfurterClient, FrankfurterError
from app.config import get_settings
from app.core.enums import BillingCycle, SpendCategory, SubscriptionStatus
from app.database import SessionFactory, init_database
from app.models.subscription import Subscription
from app.repositories.subscription_repository import SubscriptionRepository

TODAY = date.today()

# (nome, fornecedor, categoria, valor, moeda, ciclo, dias desde o inicio, dias desde o ultimo uso)
DEFAULT_SUBSCRIPTIONS = [
    ("Streaming Plus", "Acme Streaming", SpendCategory.STREAMING, Decimal("55.90"), "BRL", BillingCycle.MONTHLY, 400, 2),
    ("Music Unlimited", "Acme Audio", SpendCategory.STREAMING, Decimal("21.90"), "BRL", BillingCycle.MONTHLY, 300, 5),
    ("Cloud Backup", "Nimbus", SpendCategory.SAAS, Decimal("11.99"), "USD", BillingCycle.QUARTERLY, 500, 12),
    ("Design Suite", "Pixelworks", SpendCategory.SAAS, Decimal("29.99"), "USD", BillingCycle.MONTHLY, 220, 95),
    ("Game Pass", "Playhouse", SpendCategory.GAMING, Decimal("49.90"), "BRL", BillingCycle.MONTHLY, 180, 140),
    ("Curso de Arquitetura", "EduPro", SpendCategory.EDUCATION, Decimal("249.00"), "EUR", BillingCycle.YEARLY, 200, 30),
    ("Gym App", "FitLab", SpendCategory.HEALTH, Decimal("39.90"), "BRL", BillingCycle.MONTHLY, 260, 210),
]


async def _resolve_rate(client: FrankfurterClient, currency: str) -> tuple[Decimal, date]:
    if currency == "BRL":
        return Decimal("1"), TODAY
    try:
        return await client.fetch_rate(currency, "BRL")
    except FrankfurterError:
        # Sem rede, o seed ainda precisa funcionar: valores de referência conservadores.
        placeholders = {"USD": Decimal("5.10"), "EUR": Decimal("5.90")}
        return placeholders.get(currency, Decimal("1")), TODAY


async def seed_subscriptions() -> int:
    """Create the sample subscriptions that are still missing."""
    settings = get_settings()
    client = FrankfurterClient(settings.frankfurter_url, settings.frankfurter_timeout_seconds)

    created = 0
    async with SessionFactory() as session:
        repository = SubscriptionRepository(session)
        existing, _ = await repository.list_paginated(page_size=100)
        known_names = {item.name for item in existing}

        for name, vendor, category, amount, currency, cycle, age_days, idle_days in DEFAULT_SUBSCRIPTIONS:
            if name in known_names:
                continue

            rate, quoted_on = await _resolve_rate(client, currency)
            started_on = TODAY - timedelta(days=age_days)

            await repository.add(
                Subscription(
                    name=name,
                    vendor=vendor,
                    category=category,
                    amount=amount,
                    currency=currency,
                    billing_cycle=cycle,
                    started_on=started_on,
                    next_renewal_on=TODAY + timedelta(days=15),
                    status=SubscriptionStatus.ACTIVE,
                    last_used_on=TODAY - timedelta(days=idle_days),
                    fx_rate_to_brl=rate,
                    fx_rate_date=quoted_on,
                )
            )
            created += 1
    return created


async def _main() -> None:
    await init_database()
    created = await seed_subscriptions()
    print(f"{created} assinatura(s) criada(s).")


if __name__ == "__main__":
    asyncio.run(_main())
