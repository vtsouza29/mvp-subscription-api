"""CRUD, authentication, search, sorting and pagination for subscriptions."""

from tests.conftest import create_subscription, subscription_payload


async def test_requires_api_key(anonymous_client):
    response = await anonymous_client.get("/api/v1/subscriptions")

    assert response.status_code == 401
    assert response.json()["type"] == "http-error"


async def test_create_stores_the_exchange_rate_snapshot(client, exchange_api):
    created = await create_subscription(client, amount=10.00, currency="USD")

    assert created["currency"] == "USD"
    assert created["fx_rate_to_brl"] == 5.0
    assert created["fx_rate_date"] == "2026-09-04"
    assert created["amount_brl"] == 50.0
    assert created["monthly_amount_brl"] == 50.0
    assert created["yearly_amount_brl"] == 600.0
    assert exchange_api.rate_calls == 1


async def test_base_currency_needs_no_external_call(client, exchange_api):
    created = await create_subscription(client, amount=55.90, currency="BRL")

    assert created["fx_rate_to_brl"] == 1.0
    assert created["monthly_amount_brl"] == 55.9
    assert exchange_api.rate_calls == 0


async def test_yearly_cycle_is_normalised_to_a_monthly_cost(client):
    created = await create_subscription(client, amount=120.00, currency="BRL", billing_cycle="YEARLY")

    assert created["amount_brl"] == 120.0
    assert created["monthly_amount_brl"] == 10.0


async def test_rejects_currency_the_external_api_cannot_quote(client):
    response = await client.post(
        "/api/v1/subscriptions", json=subscription_payload(currency="XYZ")
    )

    assert response.status_code == 422
    assert response.json()["type"] == "unsupported-currency"


async def test_rejects_renewal_before_start(client):
    response = await client.post(
        "/api/v1/subscriptions",
        json=subscription_payload(started_on="2026-05-01", next_renewal_on="2026-04-01"),
    )

    assert response.status_code == 422
    assert response.json()["type"] == "validation-error"


async def test_replace_preserves_the_snapshot_when_the_price_does_not_change(client, exchange_api):
    created = await create_subscription(client, amount=10.00, currency="USD")
    assert created["amount_brl"] == 50.0
    assert exchange_api.rate_calls == 1

    renamed = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        json=subscription_payload(name="Streaming Ultra", amount=10.00, currency="USD"),
    )

    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "Streaming Ultra"
    assert body["fx_rate_to_brl"] == 5.0
    assert body["amount_brl"] == 50.0
    # Nenhuma consulta nova: o preço não mudou.
    assert exchange_api.rate_calls == 1


async def test_replace_reprices_when_the_amount_changes(client):
    created = await create_subscription(client, amount=10.00, currency="USD")

    repriced = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        json=subscription_payload(amount=20.00, currency="USD"),
    )

    assert repriced.status_code == 200
    assert repriced.json()["amount_brl"] == 100.0


async def test_changing_currency_fetches_the_new_quote(client, exchange_api):
    created = await create_subscription(client, amount=10.00, currency="USD")
    assert exchange_api.rate_calls == 1

    repriced = await client.put(
        f"/api/v1/subscriptions/{created['id']}",
        json=subscription_payload(amount=10.00, currency="EUR"),
    )

    assert repriced.status_code == 200
    body = repriced.json()
    assert body["currency"] == "EUR"
    assert body["fx_rate_to_brl"] == 6.0
    assert body["amount_brl"] == 60.0
    # A cotação do euro ainda não estava em cache, então houve consulta externa.
    assert exchange_api.rate_calls == 2


async def test_register_usage(client):
    created = await create_subscription(client, last_used_on="2026-02-01")

    response = await client.patch(
        f"/api/v1/subscriptions/{created['id']}/usage", json={"used_on": "2026-09-04"}
    )

    assert response.status_code == 200
    assert response.json()["last_used_on"] == "2026-09-04"


async def test_usage_before_start_is_rejected(client):
    created = await create_subscription(client, started_on="2026-01-10")

    response = await client.patch(
        f"/api/v1/subscriptions/{created['id']}/usage", json={"used_on": "2025-12-01"}
    )

    assert response.status_code == 422
    assert response.json()["type"] == "invalid-usage-date"


async def test_delete_subscription(client):
    created = await create_subscription(client)

    assert (await client.delete(f"/api/v1/subscriptions/{created['id']}")).status_code == 204

    missing = await client.get(f"/api/v1/subscriptions/{created['id']}")
    assert missing.status_code == 404
    assert missing.json()["type"] == "subscription-not-found"


async def test_listing_searches_filters_and_paginates(client):
    await create_subscription(client, name="Streaming Plus", currency="BRL", amount=50.00)
    await create_subscription(
        client, name="Cloud Backup", vendor="Nimbus", category="SAAS", currency="USD", amount=10.00
    )
    await create_subscription(
        client, name="Game Pass", category="GAMING", currency="BRL", amount=30.00, status="PAUSED"
    )

    found = await client.get("/api/v1/subscriptions", params={"q": "nimbus"})
    assert [item["name"] for item in found.json()["items"]] == ["Cloud Backup"]

    by_status = await client.get("/api/v1/subscriptions", params={"status": "PAUSED"})
    assert [item["name"] for item in by_status.json()["items"]] == ["Game Pass"]

    by_currency = await client.get("/api/v1/subscriptions", params={"currency": "USD"})
    assert [item["name"] for item in by_currency.json()["items"]] == ["Cloud Backup"]

    ordered = await client.get(
        "/api/v1/subscriptions", params={"sort_by": "amount", "order": "desc"}
    )
    assert [item["amount"] for item in ordered.json()["items"]] == [50.0, 30.0, 10.0]

    paginated = await client.get("/api/v1/subscriptions", params={"page": 2, "page_size": 2})
    assert paginated.json()["meta"] == {
        "page": 2,
        "page_size": 2,
        "total_items": 3,
        "total_pages": 2,
    }


async def test_usage_in_the_future_is_rejected(client):
    """Uma data futura zeraria a ociosidade para sempre."""
    created = await create_subscription(client)

    response = await client.patch(
        f"/api/v1/subscriptions/{created['id']}/usage", json={"used_on": "2099-01-01"}
    )

    assert response.status_code == 422
    assert response.json()["type"] == "invalid-usage-date"


async def test_creation_with_future_last_use_is_rejected(client):
    response = await client.post(
        "/api/v1/subscriptions", json=subscription_payload(last_used_on="2099-01-01")
    )

    assert response.status_code == 422
    assert response.json()["type"] == "validation-error"
