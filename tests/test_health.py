"""Health endpoint reports every dependency, including the ones that are down."""


async def test_health_is_public_and_reports_all_dependencies(anonymous_client):
    response = await anonymous_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "mvp-subscription-api"

    reported = {item["name"]: item["status"] for item in body["dependencies"]}
    assert reported["database"] == "up"
    assert reported["budget-api"] == "up"
    assert reported["frankfurter"] == "up"
    # Sem Redis nos testes, o cache em memória é reportado como degradado.
    assert reported["cache"] == "degraded"


async def test_health_flags_a_dependency_that_is_down(anonymous_client, budget_api, exchange_api):
    budget_api.available = False
    exchange_api.available = False

    body = (await anonymous_client.get("/health")).json()

    reported = {item["name"]: item["status"] for item in body["dependencies"]}
    assert reported["budget-api"] == "down"
    assert reported["frankfurter"] == "down"
    assert body["status"] == "degraded"
