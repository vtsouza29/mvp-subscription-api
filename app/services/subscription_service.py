"""Business rules for registering and maintaining subscriptions."""

from collections.abc import Sequence
from datetime import date, datetime, timezone

from fastapi import status

from app.core.errors import DomainError
from app.models.subscription import Subscription
from app.repositories.subscription_repository import SubscriptionRepository
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from app.services.fx_service import FxService


class SubscriptionService:
    def __init__(self, repository: SubscriptionRepository, fx_service: FxService) -> None:
        self._repository = repository
        self._fx = fx_service

    async def create(self, payload: SubscriptionCreate) -> Subscription:
        await self._fx.assert_supported(payload.currency)
        quote = await self._fx.get_quote(payload.currency)

        subscription = Subscription(
            name=payload.name,
            vendor=payload.vendor,
            category=payload.category,
            amount=payload.amount,
            currency=payload.currency,
            billing_cycle=payload.billing_cycle,
            started_on=payload.started_on,
            next_renewal_on=payload.next_renewal_on,
            status=payload.status,
            last_used_on=payload.last_used_on,
            fx_rate_to_brl=quote.rate,
            fx_rate_date=quote.quoted_on,
        )
        return await self._repository.add(subscription)

    async def get(self, subscription_id: str) -> Subscription:
        subscription = await self._repository.get_by_id(subscription_id)
        if subscription is None:
            raise DomainError(
                f"Nenhuma assinatura encontrada com o id {subscription_id}.",
                status_code=status.HTTP_404_NOT_FOUND,
                error_type="subscription-not-found",
            )
        return subscription

    async def list_paginated(self, **criteria) -> tuple[Sequence[Subscription], int]:
        return await self._repository.list_paginated(**criteria)

    async def replace(self, subscription_id: str, payload: SubscriptionUpdate) -> Subscription:
        subscription = await self.get(subscription_id)

        # A cotação só é buscada de novo quando o preço em moeda estrangeira muda:
        # o snapshot antigo continua sendo o registro correto do que foi contratado.
        repricing = (
            payload.currency != subscription.currency or payload.amount != subscription.amount
        )
        if repricing:
            await self._fx.assert_supported(payload.currency)
            quote = await self._fx.get_quote(payload.currency)
            subscription.fx_rate_to_brl = quote.rate
            subscription.fx_rate_date = quote.quoted_on

        subscription.name = payload.name
        subscription.vendor = payload.vendor
        subscription.category = payload.category
        subscription.amount = payload.amount
        subscription.currency = payload.currency
        subscription.billing_cycle = payload.billing_cycle
        subscription.started_on = payload.started_on
        subscription.next_renewal_on = payload.next_renewal_on
        subscription.status = payload.status
        subscription.last_used_on = payload.last_used_on

        return await self._repository.save(subscription)

    async def register_usage(self, subscription_id: str, used_on: date | None) -> Subscription:
        """Record that the subscription was used, which feeds the waste report."""
        subscription = await self.get(subscription_id)
        moment = used_on or datetime.now(timezone.utc).date()

        if moment < subscription.started_on:
            raise DomainError(
                "O uso não pode ser anterior ao início da assinatura.",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                error_type="invalid-usage-date",
            )

        subscription.last_used_on = moment
        return await self._repository.save(subscription)

    async def delete(self, subscription_id: str) -> None:
        subscription = await self.get(subscription_id)
        await self._repository.delete(subscription)
