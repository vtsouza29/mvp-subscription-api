"""HTTP client for the budget service, the secondary component.

Every failure is swallowed and reported as ``None``: an outage in the budget
service must degrade this API, never break it. The caller decides what to show
in place of the missing evaluation.
"""

import logging
from typing import Any

import httpx

from app.core.correlation import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class BudgetClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        retries: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._retries = max(retries, 0)

    async def evaluate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Confront the given spending with the budgets. ``None`` when unavailable."""
        return await self._post("/api/v1/evaluations", payload)

    async def project(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Ask for a spending projection. ``None`` when unavailable."""
        return await self._post("/api/v1/projections", payload)

    async def ping(self) -> bool:
        """Whether the budget service is answering, used by the health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(f"{self._base_url}/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key}

        # Propaga a correlação, para que um mesmo pedido possa ser seguido nos
        # logs dos dois serviços.
        request_id = get_request_id()
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                # Erro de contrato ou de autenticação: repetir não vai ajudar.
                logger.warning(
                    "serviço de metas respondeu %s em %s", exc.response.status_code, path
                )
                return None
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "falha ao chamar o serviço de metas em %s (tentativa %s/%s): %s",
                    path,
                    attempt + 1,
                    self._retries + 1,
                    exc,
                )

        logger.error("serviço de metas indisponível em %s: %s", path, last_error)
        return None
