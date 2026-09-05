"""Consolidated views. This is where the two services actually talk."""

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_insight_service
from app.schemas.insight import OverviewResponse, ProjectionOverview, WasteResponse
from app.security import require_api_key
from app.services.insight_service import InsightService

router = APIRouter(
    prefix="/api/v1/insights",
    tags=["Visão consolidada"],
    dependencies=[Depends(require_api_key)],
)

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Consolida o gasto mensal e confronta com as metas",
    description=(
        "Agrega o custo mensal das assinaturas ativas por categoria, já convertido para reais, "
        "e envia o resultado ao serviço de metas para avaliação. Se o serviço de metas estiver "
        "indisponível, a resposta continua sendo devolvida sem a avaliação, sinalizada em "
        "`warnings` — a indisponibilidade da componente secundária degrada esta rota, não a derruba."
    ),
)
async def overview(
    reference_month: str | None = Query(
        default=None, pattern=MONTH_PATTERN, description="Mês de referência (AAAA-MM)."
    ),
    service: InsightService = Depends(get_insight_service),
) -> OverviewResponse:
    return await service.overview(reference_month)


@router.get(
    "/waste",
    response_model=WasteResponse,
    summary="Relatório de assinaturas ociosas",
    description=(
        "Lista as assinaturas ativas sem uso registrado há mais dias que o limite informado, "
        "estimando quanto já foi pago durante o período de ociosidade."
    ),
)
async def waste(
    idle_days: int | None = Query(
        default=None, ge=1, le=3650, description="Limite de dias sem uso. Padrão: configuração do serviço."
    ),
    service: InsightService = Depends(get_insight_service),
) -> WasteResponse:
    return await service.waste(idle_days)


@router.get(
    "/projection",
    response_model=ProjectionOverview,
    summary="Projeta o desembolso das assinaturas ativas",
    description=(
        "Monta a carteira de assinaturas ativas já convertida para reais e delega a projeção "
        "ao serviço de metas, que conhece as regras de distribuição dos ciclos de cobrança."
    ),
)
async def projection(
    months: int = Query(default=12, ge=1, le=36, description="Tamanho da janela de projeção."),
    start_month: str | None = Query(
        default=None, pattern=MONTH_PATTERN, description="Primeiro mês da janela (AAAA-MM)."
    ),
    service: InsightService = Depends(get_insight_service),
) -> ProjectionOverview:
    return await service.projection(months, start_month)
