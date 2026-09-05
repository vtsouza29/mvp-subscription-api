"""Contract of the budget client: authentication, correlation, retry and failure."""

import httpx
import pytest

from app.clients.budget_client import BudgetClient
from app.core.correlation import REQUEST_ID_HEADER, _request_id


@pytest.fixture
def captured() -> list[httpx.Request]:
    return []


@pytest.fixture
def patch_transport(monkeypatch):
    """Route every httpx.AsyncClient through a mock transport."""

    def apply(handler):
        original = httpx.AsyncClient.__init__

        def patched(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    return apply


async def test_sends_the_api_key_and_propagates_the_correlation_id(patch_transport, captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"overall_status": "OK"})

    patch_transport(handler)
    token = _request_id.set("rastreio-123")
    try:
        client = BudgetClient("http://budget.test", "budget-key", 1.0, 1)
        result = await client.evaluate({"spending": []})
    finally:
        _request_id.reset(token)

    assert result == {"overall_status": "OK"}
    assert len(captured) == 1
    request = captured[0]
    assert request.url.path == "/api/v1/evaluations"
    assert request.headers["X-API-Key"] == "budget-key"
    assert request.headers[REQUEST_ID_HEADER] == "rastreio-123"


async def test_retries_once_on_a_transport_failure(patch_transport, captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        raise httpx.ConnectError("recusado", request=request)

    patch_transport(handler)
    client = BudgetClient("http://budget.test", "budget-key", 1.0, retries=1)

    assert await client.evaluate({"spending": []}) is None
    # Tentativa original mais uma retentativa.
    assert len(captured) == 2


async def test_does_not_retry_a_rejected_request(patch_transport, captured):
    """A 401 will not become a 200 on the second try; retrying only wastes time."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(401, json={"detail": "chave inválida"})

    patch_transport(handler)
    client = BudgetClient("http://budget.test", "budget-key", 1.0, retries=1)

    assert await client.evaluate({"spending": []}) is None
    assert len(captured) == 1
