"""Data access for the Subscription aggregate."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SpendCategory, SubscriptionStatus
from app.models.subscription import Subscription

SORTABLE_FIELDS = ("name", "amount", "category", "next_renewal_on", "created_at")


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, subscription_id: str) -> Subscription | None:
        return await self._session.get(Subscription, subscription_id)

    async def list_by_status(self, status: SubscriptionStatus) -> Sequence[Subscription]:
        result = await self._session.execute(
            select(Subscription).where(Subscription.status == status)
        )
        return result.scalars().all()

    async def list_paginated(
        self,
        *,
        search: str | None = None,
        category: SpendCategory | None = None,
        status: SubscriptionStatus | None = None,
        currency: str | None = None,
        sort_by: str = "name",
        order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Subscription], int]:
        """Return one page of subscriptions plus the total number of matches."""
        filters = []
        if search:
            pattern = f"%{search.lower()}%"
            filters.append(
                or_(
                    func.lower(Subscription.name).like(pattern),
                    func.lower(Subscription.vendor).like(pattern),
                )
            )
        if category is not None:
            filters.append(Subscription.category == category)
        if status is not None:
            filters.append(Subscription.status == status)
        if currency:
            filters.append(Subscription.currency == currency.upper())

        total = await self._session.scalar(
            select(func.count()).select_from(Subscription).where(*filters)
        )

        column = getattr(Subscription, sort_by if sort_by in SORTABLE_FIELDS else "name")
        ordering = column.desc() if order == "desc" else column.asc()

        result = await self._session.execute(
            select(Subscription)
            .where(*filters)
            .order_by(ordering)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return result.scalars().all(), int(total or 0)

    async def distinct_currencies(self) -> Sequence[str]:
        """Currencies actually in use, so the FX route quotes only what matters."""
        result = await self._session.execute(select(Subscription.currency).distinct())
        return result.scalars().all()

    async def add(self, subscription: Subscription) -> Subscription:
        self._session.add(subscription)
        await self._session.commit()
        await self._session.refresh(subscription)
        return subscription

    async def save(self, subscription: Subscription) -> Subscription:
        await self._session.commit()
        await self._session.refresh(subscription)
        return subscription

    async def delete(self, subscription: Subscription) -> None:
        await self._session.delete(subscription)
        await self._session.commit()
