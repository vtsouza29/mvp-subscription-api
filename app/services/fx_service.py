"""Exchange rates: fetched from the external API, treated and stored as our own.

Two cache layers sit in front of Frankfurter:

* a short-lived entry (``fx:latest``), matching the once-a-day publication of the
  ECB without hammering the API;
* a long-lived fallback (``fx:fallback``), used only when the external API is
  unreachable, so an outage degrades the answer instead of breaking it.
"""

import logging
from datetime import date
from decimal import Decimal

from fastapi import status

from app.clients.frankfurter_client import FrankfurterClient, FrankfurterError
from app.core.cache import Cache
from app.core.errors import DomainError

logger = logging.getLogger(__name__)

LATEST_NAMESPACE = "fx:latest"
FALLBACK_NAMESPACE = "fx:fallback"
CURRENCIES_KEY = "fx:currencies"


class Quote:
    """A rate plus where it came from."""

    def __init__(self, rate: Decimal, quoted_on: date, *, stale: bool = False) -> None:
        self.rate = rate
        self.quoted_on = quoted_on
        self.stale = stale


class FxService:
    def __init__(
        self,
        client: FrankfurterClient,
        cache: Cache,
        base_currency: str,
        ttl_seconds: int,
        fallback_ttl_seconds: int,
    ) -> None:
        self._client = client
        self._cache = cache
        self._base_currency = base_currency.upper()
        self._ttl = ttl_seconds
        self._fallback_ttl = fallback_ttl_seconds

    async def get_quote(self, currency: str) -> Quote:
        """Rate converting one unit of ``currency`` into the base currency."""
        currency = currency.upper()

        # A moeda base não precisa de cotação nem de chamada externa.
        if currency == self._base_currency:
            return Quote(Decimal("1"), date.today())

        cached = await self._cache.get(f"{LATEST_NAMESPACE}:{currency}")
        if cached is not None:
            return Quote(Decimal(cached["rate"]), date.fromisoformat(cached["quoted_on"]))

        try:
            rate, quoted_on = await self._client.fetch_rate(currency, self._base_currency)
        except FrankfurterError as exc:
            return await self._fallback_quote(currency, exc)

        entry = {"rate": str(rate), "quoted_on": quoted_on.isoformat()}
        await self._cache.set(f"{LATEST_NAMESPACE}:{currency}", entry, self._ttl)
        await self._cache.set(f"{FALLBACK_NAMESPACE}:{currency}", entry, self._fallback_ttl)
        return Quote(rate, quoted_on)

    async def supported_currencies(self) -> dict[str, str]:
        """Currency codes accepted by the external API, cached for a day."""
        cached = await self._cache.get(CURRENCIES_KEY)
        if cached is not None:
            return cached

        try:
            currencies = await self._client.fetch_currencies()
        except FrankfurterError as exc:
            logger.warning("não foi possível listar as moedas suportadas: %s", exc)
            return {}

        await self._cache.set(CURRENCIES_KEY, currencies, 86_400)
        return currencies

    async def assert_supported(self, currency: str) -> None:
        """Reject a currency the external API cannot quote.

        An empty list means the external API is unreachable; in that case the
        currency is accepted and validated later, when the quote is requested.
        """
        currency = currency.upper()
        if currency == self._base_currency:
            return

        supported = await self.supported_currencies()
        if supported and currency not in supported:
            raise DomainError(
                f"A moeda {currency} não é cotada pela API de câmbio utilizada.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_type="unsupported-currency",
            )

    async def _fallback_quote(self, currency: str, error: Exception) -> Quote:
        """Last known rate, or a clear failure when there is none."""
        fallback = await self._cache.get(f"{FALLBACK_NAMESPACE}:{currency}")
        if fallback is not None:
            logger.warning(
                "API de câmbio indisponível (%s); usando a última cotação conhecida de %s",
                error,
                currency,
            )
            return Quote(
                Decimal(fallback["rate"]),
                date.fromisoformat(fallback["quoted_on"]),
                stale=True,
            )

        raise DomainError(
            f"A cotação de {currency} não pôde ser obtida e não há cotação anterior em cache.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_type="exchange-rate-unavailable",
        )
