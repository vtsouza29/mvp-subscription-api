"""CRUD routes for the Subscription aggregate."""

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.enums import SpendCategory, SubscriptionStatus
from app.dependencies import get_subscription_service
from app.repositories.subscription_repository import SORTABLE_FIELDS
from app.schemas.common import Page, PageMeta
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
    UsageUpdate,
)
from app.security import require_api_key
from app.services.subscription_service import SubscriptionService

router = APIRouter(
    prefix="/api/v1/subscriptions",
    tags=["Assinaturas"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma assinatura",
    description=(
        "Registra a assinatura na moeda original e consulta a API externa de câmbio para "
        "guardar a cotação vigente. A cotação fica gravada junto do registro, preservando "
        "quanto a assinatura custava quando foi contratada."
    ),
)
async def create_subscription(
    payload: SubscriptionCreate,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    subscription = await service.create(payload)
    return SubscriptionResponse.model_validate(subscription)


@router.get(
    "",
    response_model=Page[SubscriptionResponse],
    summary="Lista assinaturas com busca, filtro, ordenação e paginação",
)
async def list_subscriptions(
    q: str | None = Query(default=None, description="Busca textual por nome ou fornecedor."),
    category: SpendCategory | None = Query(default=None, description="Filtra por categoria."),
    subscription_status: SubscriptionStatus | None = Query(
        default=None, alias="status", description="Filtra por situação."
    ),
    currency: str | None = Query(default=None, min_length=3, max_length=3, description="Filtra por moeda."),
    sort_by: str = Query(default="name", description=f"Campo de ordenação: {', '.join(SORTABLE_FIELDS)}."),
    order: str = Query(default="asc", pattern="^(asc|desc)$", description="Sentido da ordenação."),
    page: int = Query(default=1, ge=1, description="Página desejada."),
    page_size: int = Query(default=20, ge=1, le=100, description="Itens por página."),
    service: SubscriptionService = Depends(get_subscription_service),
) -> Page[SubscriptionResponse]:
    subscriptions, total = await service.list_paginated(
        search=q,
        category=category,
        status=subscription_status,
        currency=currency,
        sort_by=sort_by,
        order=order,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size
    return Page[SubscriptionResponse](
        items=[SubscriptionResponse.model_validate(item) for item in subscriptions],
        meta=PageMeta(page=page, page_size=page_size, total_items=total, total_pages=total_pages),
    )


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Consulta uma assinatura pelo identificador",
)
async def get_subscription(
    subscription_id: str,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    subscription = await service.get(subscription_id)
    return SubscriptionResponse.model_validate(subscription)


@router.put(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
    summary="Substitui uma assinatura existente",
    description=(
        "Substitui integralmente os dados da assinatura. A cotação só é buscada novamente "
        "quando o valor ou a moeda mudam; caso contrário o snapshot original é preservado."
    ),
)
async def replace_subscription(
    subscription_id: str,
    payload: SubscriptionUpdate,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    subscription = await service.replace(subscription_id, payload)
    return SubscriptionResponse.model_validate(subscription)


@router.patch(
    "/{subscription_id}/usage",
    response_model=SubscriptionResponse,
    summary="Registra o uso de uma assinatura",
    description="Atualiza a data do último uso, que alimenta o relatório de desperdício.",
)
async def register_usage(
    subscription_id: str,
    payload: UsageUpdate,
    service: SubscriptionService = Depends(get_subscription_service),
) -> SubscriptionResponse:
    subscription = await service.register_usage(subscription_id, payload.used_on)
    return SubscriptionResponse.model_validate(subscription)


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove uma assinatura",
)
async def delete_subscription(
    subscription_id: str,
    service: SubscriptionService = Depends(get_subscription_service),
) -> Response:
    await service.delete(subscription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
