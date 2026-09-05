"""Consumption of the external exchange-rate API: cache, fallback and failure."""

from tests.conftest import create_subscription, subscription_payload


async def test_rates_route_quotes_only_the_currencies_in_use(client):
    await create_subscription(client, name="Cloud Backup", currency="USD", amount=10.00)
    await create_subscription(client, name="Streaming Plus", currency="BRL", amount=50.00)

    response = await client.get("/api/v1/fx/rates")

    assert response.status_code == 200
    body = response.json()
    assert body["base_currency"] == "BRL"
    assert body["source"].startswith("Frankfurter")
    assert {rate["currency"]: rate["rate_to_brl"] for rate in body["rates"]} == {
        "BRL": 1.0,
        "USD": 5.0,
    }


async def test_quote_is_cached_between_calls(client, exchange_api):
    await create_subscription(client, currency="USD", amount=10.00)
    assert exchange_api.rate_calls == 1

    await client.get("/api/v1/fx/rates")
    await client.get("/api/v1/fx/rates")

    # A cotação do dólar foi buscada uma única vez.
    assert exchange_api.rate_calls == 1


async def test_creation_fails_clearly_when_the_external_api_is_down(client, exchange_api):
    exchange_api.available = False

    response = await client.post("/api/v1/subscriptions", json=subscription_payload(currency="USD"))

    assert response.status_code == 503
    assert response.json()["type"] == "exchange-rate-unavailable"


async def test_last_known_quote_is_used_when_the_external_api_falls(client, app_instance, exchange_api):
    """An outage must degrade the answer, not break it."""
    await create_subscription(client, name="Cloud Backup", currency="USD", amount=10.00)

    # Derruba a API externa e expira o cache de curta duração.
    exchange_api.available = False
    app_instance.state.cache._entries.pop("fx:latest:USD", None)

    response = await client.get("/api/v1/fx/rates")

    assert response.status_code == 200
    body = response.json()
    usd = next(rate for rate in body["rates"] if rate["currency"] == "USD")
    assert usd["stale"] is True
    assert usd["rate_to_brl"] == 5.0
    assert any("cache de emergência" in warning for warning in body["warnings"])


async def test_currency_validation_is_skipped_when_the_external_api_is_down(client, exchange_api):
    """Without the currency list there is nothing to validate against.

    The rate itself still has to resolve, so a genuinely unknown currency fails
    later, on the quote, rather than being silently accepted.
    """
    await create_subscription(client, currency="USD", amount=10.00)
    exchange_api.available = False

    response = await client.post(
        "/api/v1/subscriptions", json=subscription_payload(name="Outra", currency="USD")
    )

    # A cotação do dólar segue no cache, então o cadastro é aceito.
    assert response.status_code == 201
    assert response.json()["fx_rate_to_brl"] == 5.0
