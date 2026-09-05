"""Request and response schemas for the Subscription aggregate."""

from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from app.core.enums import BillingCycle, SpendCategory, SubscriptionStatus
from app.schemas.common import MoneyIn, to_money


class SubscriptionBase(BaseModel):
    """Fields a client may set, shared by creation and full replacement."""

    name: str = Field(min_length=1, max_length=120, examples=["Streaming Plus"])
    vendor: str = Field(min_length=1, max_length=120, examples=["Acme Streaming"])
    category: SpendCategory
    amount: MoneyIn = Field(description="Valor de cada cobrança, na moeda original.")
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="Código ISO-4217 da moeda, entre as suportadas pela API de câmbio.",
        examples=["USD"],
    )
    billing_cycle: BillingCycle
    started_on: date = Field(description="Data em que a assinatura começou.")
    next_renewal_on: date = Field(description="Data da próxima cobrança.")
    status: SubscriptionStatus = Field(default=SubscriptionStatus.ACTIVE)
    last_used_on: date | None = Field(
        default=None, description="Último uso registrado. Vazio significa nunca usada."
    )

    @field_validator("currency")
    @classmethod
    def _normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("A moeda deve conter apenas letras.")
        return normalized

    @model_validator(mode="after")
    def _check_dates(self) -> "SubscriptionBase":
        if self.next_renewal_on < self.started_on:
            raise ValueError("A próxima renovação não pode ser anterior ao início da assinatura.")
        if self.last_used_on and self.last_used_on < self.started_on:
            raise ValueError("O último uso não pode ser anterior ao início da assinatura.")
        return self


class SubscriptionCreate(SubscriptionBase):
    """Payload to register a new subscription."""


class SubscriptionUpdate(SubscriptionBase):
    """Full replacement payload, matching PUT semantics."""


class UsageUpdate(BaseModel):
    """Payload of the usage route: records that the subscription was used."""

    used_on: date | None = Field(
        default=None, description="Data do uso. Vazio registra o dia de hoje."
    )


class SubscriptionResponse(BaseModel):
    """Subscription as returned by the API, with the derived amounts."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    vendor: str
    category: SpendCategory
    amount: float = Field(description="Valor da cobrança na moeda original.")
    currency: str
    billing_cycle: BillingCycle
    started_on: date
    next_renewal_on: date
    status: SubscriptionStatus
    last_used_on: date | None

    fx_rate_to_brl: float = Field(description="Cotação registrada no momento do cadastro.")
    fx_rate_date: date = Field(description="Data de publicação da cotação pelo BCE.")

    amount_brl: float = Field(description="Valor de cada cobrança em reais.")
    monthly_amount_brl: float = Field(description="Custo normalizado por mês, em reais.")
    yearly_amount_brl: float = Field(description="Custo normalizado por ano, em reais.")
    idle_days: int = Field(description="Dias desde o último uso registrado.")

    created_at: datetime
    updated_at: datetime

    @field_serializer("amount", "amount_brl", "monthly_amount_brl", "yearly_amount_brl")
    def _serialize_money(self, value: float) -> float:
        return to_money(value)

    @field_serializer("fx_rate_to_brl")
    def _serialize_rate(self, value: float) -> float:
        return round(float(value), 6)
