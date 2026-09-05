"""The Subscription aggregate: one recurring charge the user pays for."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import BillingCycle, SpendCategory, SubscriptionStatus
from app.core.types import MoneyType, RateType
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Subscription(Base):
    """A subscription priced in its original currency.

    ``amount`` and ``currency`` are the source of truth. ``fx_rate_to_brl`` and
    ``fx_rate_date`` are a *snapshot* of the exchange rate taken when the record
    was created or repriced: the external quote is consumed, transformed and
    stored as our own data, never merely proxied.
    """

    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[SpendCategory] = mapped_column(
        SAEnum(SpendCategory, native_enum=False, length=20), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(MoneyType, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        SAEnum(BillingCycle, native_enum=False, length=20), nullable=False
    )
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    next_renewal_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(SubscriptionStatus, native_enum=False, length=20),
        nullable=False,
        index=True,
        default=SubscriptionStatus.ACTIVE,
    )
    last_used_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    fx_rate_to_brl: Mapped[Decimal] = mapped_column(RateType, nullable=False)
    fx_rate_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # --- Valores derivados: calculados, nunca persistidos ---

    @property
    def amount_brl(self) -> Decimal:
        """Value of a single charge, converted with the stored snapshot."""
        return self.amount * self.fx_rate_to_brl

    @property
    def monthly_amount_brl(self) -> Decimal:
        """Charge normalised to a monthly cost, so cycles become comparable."""
        return self.amount_brl / self.billing_cycle.month_step

    @property
    def yearly_amount_brl(self) -> Decimal:
        return self.monthly_amount_brl * 12

    def idle_days_since(self, reference: date | None = None) -> int:
        """Days since the last recorded use, counting from the start if never used."""
        today = reference or datetime.now(timezone.utc).date()
        baseline = self.last_used_on or self.started_on
        return max((today - baseline).days, 0)

    @property
    def idle_days(self) -> int:
        return self.idle_days_since()

    def __repr__(self) -> str:  # pragma: no cover - conveniência de debug
        return f"<Subscription {self.name} {self.amount} {self.currency}>"
