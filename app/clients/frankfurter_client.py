"""HTTP client for Frankfurter, the external exchange-rate API.

Frankfurter publishes the reference rates of the European Central Bank. It is
free, needs no registration and no API key, which is why it was chosen for this
MVP: nothing to leak into a public repository.
"""

import logging
from datetime import date
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)


class FrankfurterError(RuntimeError):
    """The external API could not be reached or answered unexpectedly."""


class FrankfurterClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_rate(self, currency: str, target: str = "BRL") -> tuple[Decimal, date]:
        """Return how much one unit of ``currency`` is worth in ``target``.

        Also returns the date the quote refers to, which is the ECB publication
        date and not the moment of the call: rates are published once per
        business day.
        """
        url = f"{self._base_url}/latest"
        params = {"base": currency.upper(), "symbols": target.upper()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise FrankfurterError(f"Falha ao consultar a API de câmbio: {exc}") from exc

        try:
            rate = Decimal(str(payload["rates"][target.upper()]))
            quoted_on = date.fromisoformat(payload["date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FrankfurterError(
                f"Resposta inesperada da API de câmbio para {currency}: {payload}"
            ) from exc

        return rate, quoted_on

    async def fetch_currencies(self) -> dict[str, str]:
        """Currency codes supported by the external API, mapped to their names."""
        url = f"{self._base_url}/currencies"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise FrankfurterError(f"Falha ao listar moedas suportadas: {exc}") from exc
