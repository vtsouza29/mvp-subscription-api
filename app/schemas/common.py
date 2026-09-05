"""Building blocks reused by every response schema."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

_CENTS = Decimal("0.01")

#: Monetary input: strictly positive, at most two decimal places.
MoneyIn = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]

#: Monetary input that may legitimately be zero (observed spending, for instance).
MoneyInOrZero = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


def to_money(value: Decimal) -> float:
    """Round a decimal amount to cents and emit it as a JSON number.

    Arithmetic stays in ``Decimal``; only the API boundary converts, so responses
    carry numbers rather than quoted strings.
    """
    return float(Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP))


def to_pct(value: Decimal) -> float:
    """Round a percentage to two decimal places."""
    return float(Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP))


class PageMeta(BaseModel):
    """Pagination envelope returned alongside every listing."""

    page: int = Field(description="Página atual, começando em 1.")
    page_size: int = Field(description="Quantidade de itens por página.")
    total_items: int = Field(description="Total de itens que satisfazem o filtro.")
    total_pages: int = Field(description="Total de páginas disponíveis.")


class Page(BaseModel, Generic[T]):
    """Paginated listing."""

    items: list[T]
    meta: PageMeta


class DependencyHealth(BaseModel):
    """State of one external dependency of this service."""

    name: str
    status: str = Field(description="'up', 'down' ou 'degraded'.")
    detail: str | None = None


class HealthResponse(BaseModel):
    """Liveness plus the real state of each dependency."""

    status: str = Field(description="'healthy' ou 'degraded'.")
    service: str
    version: str
    dependencies: list[DependencyHealth]
