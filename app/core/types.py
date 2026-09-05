"""Custom SQLAlchemy column types."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Integer
from sqlalchemy.types import TypeDecorator

_CENTS = Decimal("0.01")


class MoneyType(TypeDecorator):
    """Store a monetary amount as an integer number of cents.

    SQLite has no native decimal type, so persisting ``Numeric`` there round-trips
    through float and loses precision. Cents keep the value exact and still sort
    correctly in ``ORDER BY``.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect) -> int | None:
        if value is None:
            return None
        quantized = Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return int(quantized * 100)

    def process_result_value(self, value: int | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(value) / 100).quantize(_CENTS)


_RATE_PRECISION = Decimal("0.000001")
_RATE_SCALE = 1_000_000


class RateType(TypeDecorator):
    """Store an exchange rate as an integer scaled by one million.

    Same reasoning as :class:`MoneyType`, with the extra precision a quote needs:
    six decimal places comfortably cover the rates published by the ECB.
    """

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect) -> int | None:
        if value is None:
            return None
        quantized = Decimal(value).quantize(_RATE_PRECISION, rounding=ROUND_HALF_UP)
        return int(quantized * _RATE_SCALE)

    def process_result_value(self, value: int | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(value) / _RATE_SCALE).quantize(_RATE_PRECISION)
