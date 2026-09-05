"""Schemas for the consolidated views that orchestrate the budget service."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import SpendCategory


class CategorySpend(BaseModel):
    """Monthly spending consolidated for one category."""

    category: SpendCategory
    monthly_amount_brl: float
    subscription_count: int
    share_pct: float = Field(description="Participação da categoria no gasto total.")


class OverviewResponse(BaseModel):
    """Consolidated spending plus the budget evaluation, when available."""

    generated_at: datetime
    reference_month: str
    active_subscriptions: int
    total_monthly_brl: float
    total_yearly_brl: float
    by_category: list[CategorySpend]
    budget_evaluation: dict[str, Any] | None = Field(
        default=None,
        description="Resposta do serviço de metas. Nulo quando o serviço está indisponível.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Limitações desta resposta, como a ausência da avaliação de metas.",
    )


class WasteItem(BaseModel):
    """An active subscription that is being paid for and not used."""

    id: str
    name: str
    vendor: str
    category: SpendCategory
    monthly_amount_brl: float
    last_used_on: date | None
    idle_days: int
    wasted_brl: float = Field(description="Valor estimado pago durante o período ocioso.")


class WasteResponse(BaseModel):
    """Idle-subscription report."""

    generated_at: datetime
    idle_days_threshold: int
    idle_subscriptions: int
    wasted_monthly_brl: float = Field(description="Gasto mensal preso em assinaturas ociosas.")
    total_wasted_brl: float = Field(description="Valor estimado já desperdiçado.")
    items: list[WasteItem]


class ProjectionOverview(BaseModel):
    """Projection produced by the budget service from the active subscriptions."""

    generated_at: datetime
    months: int
    subscriptions_considered: int
    projection: dict[str, Any] | None = Field(
        default=None,
        description="Resposta do serviço de metas. Nulo quando o serviço está indisponível.",
    )
    warnings: list[str] = Field(default_factory=list)
