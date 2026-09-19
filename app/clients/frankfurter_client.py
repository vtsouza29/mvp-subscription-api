"""HTTP client for Frankfurter, the external exchange-rate API.

Frankfurter publishes the reference rates of the European Central Bank. It is
free, needs no registration and no API key, which is why it was chosen for this
MVP: nothing to leak into a public repository.

The client talks to the **v2** API, through the ``ecb`` provider routes. v2 also
aggregates other providers, but this application quotes ECB reference rates, so
the provider is pinned instead of left to the default.
"""

import logging
from datetime import date
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

PROVIDER = "ecb"


class FrankfurterError(RuntimeError):
    """The external API could not be reached or answered unexpectedly."""


class FrankfurterClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def _get(self, path: str, params: dict[str, str] | None = None) -> object:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise FrankfurterError(f"Falha ao consultar a API de câmbio: {exc}") from exc

    async def fetch_rate(self, currency: str, target: str = "BRL") -> tuple[Decimal, date]:
        """Return how much one unit of ``currency`` is worth in ``target``.

        Also returns the date the quote refers to, which is the ECB publication
        date and not the moment of the call: rates are published once per
        business day.
        """
        payload = await self._get(f"/providers/{PROVIDER}/rate/{currency.lower()}/{target.lower()}")

        try:
            rate = Decimal(str(payload["rate"]))
            quoted_on = date.fromisoformat(payload["date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FrankfurterError(
                f"Resposta inesperada da API de câmbio para {currency}: {payload}"
            ) from exc

        return rate, quoted_on

    async def fetch_currencies(self) -> dict[str, str]:
        """Currency codes quoted by the ECB, mapped to themselves.

        v2 lists rates per provider instead of a name dictionary, so the codes
        come from the quotes published against the euro. The mapping shape is
        kept because the service uses it to validate a currency.
        """
        payload = await self._get(f"/providers/{PROVIDER}/rates", {"base": "EUR"})

        try:
            codes = {str(item["quote"]).upper() for item in payload}
        except (KeyError, TypeError) as exc:
            raise FrankfurterError(f"Resposta inesperada ao listar moedas: {payload}") from exc

        return {code: code for code in sorted(codes)}
