"""Schemas exposing the treated exchange-rate data."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class FxRate(BaseModel):
    """One quote, already converted into the shape this application uses."""

    currency: str = Field(description="Moeda de origem.")
    rate_to_brl: float = Field(description="Quanto vale uma unidade da moeda, em reais.")
    quoted_on: date = Field(description="Data de publicação da cotação pelo BCE.")
    stale: bool = Field(
        default=False,
        description="Verdadeiro quando a API externa falhou e foi usada a última cotação conhecida.",
    )


class FxRatesResponse(BaseModel):
    """Quotes for the currencies actually in use by the registered subscriptions."""

    base_currency: str
    retrieved_at: datetime
    source: str = Field(description="Origem dos dados.")
    rates: list[FxRate]
    warnings: list[str] = Field(default_factory=list)
