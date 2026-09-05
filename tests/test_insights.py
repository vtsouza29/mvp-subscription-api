"""Consolidated views and the conversation with the budget service."""

from tests.conftest import create_subscription


async def test_overview_aggregates_by_category_and_calls_the_budget_service(client, budget_api):
    await create_subscription(client, name="Streaming Plus", category="STREAMING", currency="BRL", amount=60.00)
    await create_subscription(client, name="Music", category="STREAMING", currency="BRL", amount=20.00)
    await create_subscription(client, name="Cloud", category="SAAS", currency="USD", amount=4.00)

    response = await client.get("/api/v1/insights/overview", params={"reference_month": "2026-09"})

    assert response.status_code == 200
    body = response.json()
    assert body["active_subscriptions"] == 3
    assert body["total_monthly_brl"] == 100.0
    assert body["total_yearly_brl"] == 1200.0

    by_category = {item["category"]: item for item in body["by_category"]}
    assert by_category["STREAMING"]["monthly_amount_brl"] == 80.0
    assert by_category["STREAMING"]["subscription_count"] == 2
    assert by_category["STREAMING"]["share_pct"] == 80.0
    assert by_category["SAAS"]["monthly_amount_brl"] == 20.0

    assert body["budget_evaluation"] == {
        "overall_status": "OK",
        "results": [],
        "unbudgeted_categories": [],
    }
    assert body["warnings"] == []

    # O payload enviado ao serviço de metas já vai convertido para reais.
    sent = budget_api.last_evaluation_payload
    assert sent["reference_month"] == "2026-09"
    assert sorted(entry["category"] for entry in sent["spending"]) == ["SAAS", "STREAMING"]


async def test_overview_degrades_when_the_budget_service_is_down(client, budget_api):
    await create_subscription(client, currency="BRL", amount=50.00)
    budget_api.available = False

    response = await client.get("/api/v1/insights/overview")

    assert response.status_code == 200
    body = response.json()
    # O gasto local continua sendo consolidado normalmente.
    assert body["total_monthly_brl"] == 50.0
    assert body["budget_evaluation"] is None
    assert len(body["warnings"]) == 1
    assert "indisponível" in body["warnings"][0]


async def test_paused_subscriptions_are_not_counted(client):
    await create_subscription(client, name="Ativa", currency="BRL", amount=50.00)
    await create_subscription(client, name="Pausada", currency="BRL", amount=90.00, status="PAUSED")

    body = (await client.get("/api/v1/insights/overview")).json()

    assert body["active_subscriptions"] == 1
    assert body["total_monthly_brl"] == 50.0


async def test_waste_report_lists_idle_subscriptions(client):
    await create_subscription(
        client, name="Usada ontem", currency="BRL", amount=50.00,
        started_on="2026-01-01", last_used_on="2026-09-04",
    )
    await create_subscription(
        client, name="Esquecida", currency="BRL", amount=30.00,
        started_on="2026-01-01", last_used_on="2026-01-15",
    )

    response = await client.get("/api/v1/insights/waste", params={"idle_days": 30})

    assert response.status_code == 200
    body = response.json()
    assert body["idle_days_threshold"] == 30
    assert body["idle_subscriptions"] == 1
    assert body["wasted_monthly_brl"] == 30.0

    item = body["items"][0]
    assert item["name"] == "Esquecida"
    assert item["idle_days"] > 30
    assert item["wasted_brl"] > 0


async def test_never_used_subscription_counts_from_the_start_date(client):
    await create_subscription(
        client, name="Nunca usada", currency="BRL", amount=25.00,
        started_on="2026-01-01", last_used_on=None,
    )

    body = (await client.get("/api/v1/insights/waste", params={"idle_days": 30})).json()

    assert body["idle_subscriptions"] == 1
    assert body["items"][0]["last_used_on"] is None


async def test_projection_is_delegated_to_the_budget_service(client, budget_api):
    await create_subscription(
        client, name="Cloud Backup", currency="USD", amount=10.00,
        billing_cycle="QUARTERLY", next_renewal_on="2026-10-01",
    )

    response = await client.get(
        "/api/v1/insights/projection", params={"months": 6, "start_month": "2026-09"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subscriptions_considered"] == 1
    assert body["projection"]["total_brl"] == 1234.0

    # A conversão para reais acontece aqui; o serviço de metas recebe tudo em BRL.
    sent = budget_api.last_projection_payload
    assert sent["months"] == 6
    assert sent["start_month"] == "2026-09"
    assert sent["subscriptions"][0] == {
        "name": "Cloud Backup",
        "category": "STREAMING",
        "amount_brl": 50.0,
        "billing_cycle": "QUARTERLY",
        "next_renewal_on": "2026-10-01",
    }


async def test_projection_degrades_when_the_budget_service_is_down(client, budget_api):
    await create_subscription(client, currency="BRL", amount=50.00)
    budget_api.available = False

    body = (await client.get("/api/v1/insights/projection")).json()

    assert body["projection"] is None
    assert "indisponível" in body["warnings"][0]
