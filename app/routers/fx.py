"""Exchange-rate data, consumed from the external API and served as our own."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.errors import DomainError
from app.dependencies import get_fx_service, get_subscription_repository
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.fx import FxRate, FxRatesResponse
from app.security import require_api_key
from app.services.fx_service import FxService

router = APIRouter(
    prefix="/api/v1/fx",
    tags=["Câmbio"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/rates",
    response_model=FxRatesResponse,
    summary="Cotações das moedas em uso pelas assinaturas",
    description=(
        "Consulta a API externa de câmbio apenas para as moedas efetivamente utilizadas pelas "
        "assinaturas cadastradas, trata o resultado e o devolve no formato desta aplicação. "
        "Se a API externa falhar, é usada a última cotação conhecida, marcada com `stale`."
    ),
)
async def list_rates(
    repository: SubscriptionRepository = Depends(get_subscription_repository),
    fx_service: FxService = Depends(get_fx_service),
) -> FxRatesResponse:
    currencies = sorted({code.upper() for code in await repository.distinct_currencies()})

    rates: list[FxRate] = []
    warnings: list[str] = []

    for currency in currencies:
        try:
            quote = await fx_service.get_quote(currency)
        except DomainError as exc:
            warnings.append(exc.detail)
            continue

        rates.append(
            FxRate(
                currency=currency,
                rate_to_brl=round(float(quote.rate), 6),
                quoted_on=quote.quoted_on,
                stale=quote.stale,
            )
        )

    if any(rate.stale for rate in rates):
        warnings.append(
            "Ao menos uma cotação veio do cache de emergência por indisponibilidade da API externa."
        )

    return FxRatesResponse(
        base_currency="BRL",
        retrieved_at=datetime.now(timezone.utc),
        source="Frankfurter (Banco Central Europeu)",
        rates=rates,
        warnings=warnings,
    )
