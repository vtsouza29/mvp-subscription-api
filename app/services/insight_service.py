"""Consolidated views that combine local data with the budget service."""

from datetime import datetime, timezone
from decimal import Decimal

from app.clients.budget_client import BudgetClient
from app.core.enums import SubscriptionStatus
from app.models.subscription import Subscription
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.common import to_money, to_pct
from app.schemas.insight import (
    CategorySpend,
    OverviewResponse,
    ProjectionOverview,
    WasteItem,
    WasteResponse,
)

BUDGET_UNAVAILABLE = (
    "O serviço de metas está indisponível; a resposta foi montada sem a avaliação de orçamento."
)


class InsightService:
    def __init__(
        self,
        repository: SubscriptionRepository,
        budget_client: BudgetClient,
        idle_days_threshold: int,
    ) -> None:
        self._repository = repository
        self._budget = budget_client
        self._idle_days_threshold = idle_days_threshold

    async def overview(self, reference_month: str | None = None) -> OverviewResponse:
        """Spending by category, confronted with the budgets when possible."""
        active = await self._repository.list_by_status(SubscriptionStatus.ACTIVE)
        month = reference_month or _current_month()

        totals: dict = {}
        total_monthly = Decimal("0")
        for subscription in active:
            monthly = subscription.monthly_amount_brl
            total_monthly += monthly
            amount, count = totals.get(subscription.category, (Decimal("0"), 0))
            totals[subscription.category] = (amount + monthly, count + 1)

        by_category = [
            CategorySpend(
                category=category,
                monthly_amount_brl=to_money(amount),
                subscription_count=count,
                share_pct=to_pct(amount / total_monthly * 100) if total_monthly else 0.0,
            )
            for category, (amount, count) in sorted(
                totals.items(), key=lambda item: item[1][0], reverse=True
            )
        ]

        evaluation = None
        warnings: list[str] = []
        if by_category:
            evaluation = await self._budget.evaluate(
                {
                    "reference_month": month,
                    "spending": [
                        {
                            "category": entry.category.value,
                            "monthly_amount_brl": entry.monthly_amount_brl,
                        }
                        for entry in by_category
                    ],
                }
            )
            if evaluation is None:
                warnings.append(BUDGET_UNAVAILABLE)

        return OverviewResponse(
            generated_at=datetime.now(timezone.utc),
            reference_month=month,
            active_subscriptions=len(active),
            total_monthly_brl=to_money(total_monthly),
            total_yearly_brl=to_money(total_monthly * 12),
            by_category=by_category,
            budget_evaluation=evaluation,
            warnings=warnings,
        )

    async def waste(self, idle_days_threshold: int | None = None) -> WasteResponse:
        """Active subscriptions nobody has used for a while.

        Computed locally: it depends only on data this service owns.
        """
        threshold = idle_days_threshold or self._idle_days_threshold
        active = await self._repository.list_by_status(SubscriptionStatus.ACTIVE)

        items: list[WasteItem] = []
        wasted_monthly = Decimal("0")
        total_wasted = Decimal("0")

        for subscription in active:
            idle_days = subscription.idle_days
            if idle_days < threshold:
                continue

            monthly = subscription.monthly_amount_brl
            wasted = monthly * Decimal(idle_days) / Decimal(30)
            wasted_monthly += monthly
            total_wasted += wasted

            items.append(
                WasteItem(
                    id=subscription.id,
                    name=subscription.name,
                    vendor=subscription.vendor,
                    category=subscription.category,
                    monthly_amount_brl=to_money(monthly),
                    last_used_on=subscription.last_used_on,
                    idle_days=idle_days,
                    wasted_brl=to_money(wasted),
                )
            )

        items.sort(key=lambda item: item.wasted_brl, reverse=True)

        return WasteResponse(
            generated_at=datetime.now(timezone.utc),
            idle_days_threshold=threshold,
            idle_subscriptions=len(items),
            wasted_monthly_brl=to_money(wasted_monthly),
            total_wasted_brl=to_money(total_wasted),
            items=items,
        )

    async def projection(self, months: int, start_month: str | None = None) -> ProjectionOverview:
        """Ask the budget service to project the active subscriptions forward."""
        active = await self._repository.list_by_status(SubscriptionStatus.ACTIVE)

        payload = {
            "months": months,
            "subscriptions": [_to_projection_entry(item) for item in active],
        }
        if start_month:
            payload["start_month"] = start_month

        projection = None
        warnings: list[str] = []
        if active:
            projection = await self._budget.project(payload)
            if projection is None:
                warnings.append(BUDGET_UNAVAILABLE)
        else:
            warnings.append("Não há assinaturas ativas para projetar.")

        return ProjectionOverview(
            generated_at=datetime.now(timezone.utc),
            months=months,
            subscriptions_considered=len(active),
            projection=projection,
            warnings=warnings,
        )


def _to_projection_entry(subscription: Subscription) -> dict:
    """Shape one subscription the way the budget service expects it."""
    return {
        "name": subscription.name,
        "category": subscription.category.value,
        "amount_brl": to_money(subscription.amount_brl),
        "billing_cycle": subscription.billing_cycle.value,
        "next_renewal_on": subscription.next_renewal_on.isoformat(),
    }


def _current_month() -> str:
    today = datetime.now(timezone.utc).date()
    return f"{today.year:04d}-{today.month:02d}"
