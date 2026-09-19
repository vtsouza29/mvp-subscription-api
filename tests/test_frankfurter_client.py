"""Contrato do cliente da API externa de câmbio (Frankfurter v2)."""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.clients.frankfurter_client import FrankfurterClient, FrankfurterError

BASE_URL = "https://api.frankfurter.dev/v2"


@pytest.fixture
def patch_transport(monkeypatch):
    """Direciona todo httpx.AsyncClient para um transporte simulado."""

    def apply(handler):
        original = httpx.AsyncClient.__init__

        def patched(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    return apply


def client() -> FrankfurterClient:
    return FrankfurterClient(BASE_URL, 5.0)


async def test_cotacao_usa_a_rota_do_provedor_ecb(patch_transport):
    """A v2 agrega vários provedores; esta aplicação fixa o BCE."""
    chamadas: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url)
        return httpx.Response(
            200, json={"date": "2026-09-18", "base": "USD", "quote": "BRL", "rate": 5.1359}
        )

    patch_transport(handler)
    rate, quoted_on = await client().fetch_rate("USD", "BRL")

    assert rate == Decimal("5.1359")
    assert quoted_on == date(2026, 9, 18)
    assert chamadas[0].path == "/v2/providers/ecb/rate/usd/brl"


async def test_moedas_vem_das_cotacoes_do_bce(patch_transport):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/providers/ecb/rates"
        assert request.url.params["base"] == "EUR"
        return httpx.Response(
            200,
            json=[
                {"date": "2026-09-18", "base": "EUR", "quote": "BRL", "rate": 5.88},
                {"date": "2026-09-18", "base": "EUR", "quote": "usd", "rate": 1.14},
            ],
        )

    patch_transport(handler)
    moedas = await client().fetch_currencies()

    assert moedas == {"BRL": "BRL", "USD": "USD"}, "códigos normalizados em maiúsculas"


async def test_erro_http_vira_erro_de_dominio(patch_transport):
    patch_transport(lambda request: httpx.Response(503, json={"message": "indisponível"}))

    with pytest.raises(FrankfurterError):
        await client().fetch_rate("USD")


async def test_resposta_fora_do_formato_vira_erro_claro(patch_transport):
    """Uma resposta no formato da v1 deixa de ser aceita silenciosamente."""
    patch_transport(
        lambda request: httpx.Response(200, json={"rates": {"BRL": 5.13}, "date": "2026-09-18"})
    )

    with pytest.raises(FrankfurterError):
        await client().fetch_rate("USD")
